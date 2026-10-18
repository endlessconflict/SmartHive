"""Login, refresh rotation, logout and who sees which apiary, against a real database."""

import time
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.app import create_app
from smarthive.api.ratelimit import FailureLimiter
from smarthive.api.security import create_access_token, hash_password
from smarthive.config import Settings

pytestmark = pytest.mark.integration

SECRET = "t" * 48
PASSWORD = "correct horse battery"


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE refresh_tokens CASCADE"))
    app = create_app(Settings(jwt_secret=SECRET, login_max_failures=3, login_window_s=60), engine)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False, client=("203.0.113.9", 4000))
    async with httpx.AsyncClient(
        transport=transport, base_url="https://api.test"
    ) as c:  # https: the cookie is Secure
        c.app = app  # type: ignore[attr-defined]
        yield c


async def add_user(engine: AsyncEngine, email: str, role: str = "beekeeper") -> UUID:
    user = uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, display_name, password_hash, role) VALUES (:i, :e, :n, :h, :r)"
            ),
            {"i": user, "e": email, "n": email.split("@")[0], "h": hash_password(PASSWORD), "r": role},
        )
    return user


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(response: httpx.Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_login_gives_a_token_that_opens_the_profile(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    await add_user(engine, "ana@example.com", "admin")
    r = await login(client, "ANA@example.com")  # the email column is case-insensitive
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer" and r.json()["expires_in"] == 900
    me = await client.get("/api/v1/me", headers=bearer(r))
    assert me.status_code == 200 and me.json()["email"] == "ana@example.com" and me.json()["role"] == "admin"
    assert "password_hash" not in me.json()


async def test_the_refresh_cookie_is_locked_down(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    await add_user(engine, "ana@example.com")
    cookie = (await login(client, "ana@example.com")).headers["set-cookie"].lower()
    assert "refresh_token=" in cookie
    for attribute in ("httponly", "secure", "samesite=strict", "path=/api/v1/auth"):
        assert attribute in cookie


async def test_wrong_password_and_unknown_user_look_the_same(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    await add_user(engine, "ana@example.com")
    wrong = await login(client, "ana@example.com", "nope")
    unknown = await login(client, "nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert (
        wrong.json()
        == unknown.json()
        == {"type": "about:blank", "title": "Invalid email or password", "status": 401}
    )
    assert "set-cookie" not in wrong.headers


async def test_repeated_failures_block_the_client_even_with_the_right_password(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    await add_user(engine, "ana@example.com")
    for _ in range(3):
        assert (await login(client, "ana@example.com", "nope")).status_code == 401
    blocked = await login(client, "ana@example.com")
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    client.app.state.login_limiter = FailureLimiter(3, 60)  # type: ignore[attr-defined]
    assert (await login(client, "ana@example.com")).status_code == 200


async def test_refresh_rotates_the_cookie_and_the_old_one_stops_working(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    await add_user(engine, "ana@example.com")
    first = (await login(client, "ana@example.com")).cookies["refresh_token"]
    second = await client.post("/api/v1/auth/refresh")
    assert second.status_code == 200 and "access_token" in second.json()
    assert client.cookies["refresh_token"] != first


async def test_a_refresh_token_used_twice_closes_every_session_of_that_user(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    await add_user(engine, "ana@example.com")
    stolen = (await login(client, "ana@example.com")).cookies["refresh_token"]
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200  # the real owner rotates it
    replay = await client.post(
        "/api/v1/auth/refresh", cookies={"refresh_token": stolen}
    )  # a thief replays it
    assert replay.status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401  # the owner's new token died too
    async with engine.connect() as conn:
        open_sessions = (
            await conn.execute(text("SELECT count(*) FROM refresh_tokens WHERE revoked_at IS NULL"))
        ).scalar_one()
    assert open_sessions == 0


async def test_refresh_without_a_cookie_or_with_a_made_up_one_is_refused(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", cookies={"refresh_token": "made-up"})
    ).status_code == 401


async def test_an_expired_refresh_token_is_refused(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    await add_user(engine, "ana@example.com")
    await login(client, "ana@example.com")
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE refresh_tokens SET expires_at = now() - interval '1 second'"))
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_revokes_the_session(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    await add_user(engine, "ana@example.com")
    cookie = (await login(client, "ana@example.com")).cookies["refresh_token"]
    out = await client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    assert (await client.post("/api/v1/auth/refresh", cookies={"refresh_token": cookie})).status_code == 401
    assert (await client.post("/api/v1/auth/logout")).status_code == 204  # idempotent


async def test_bad_access_tokens_are_refused(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    user = await add_user(engine, "ana@example.com")
    expired = create_access_token(SECRET, user, "beekeeper", 15, now=time.time() - 3600)
    foreign = create_access_token("z" * 48, user, "beekeeper", 15)
    for token in (expired, foreign, "garbage"):
        r = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


async def test_a_token_of_a_deleted_user_is_refused(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    user = await add_user(engine, "ana@example.com")
    token = create_access_token(SECRET, user, "admin", 15)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": user})
    assert (await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401


async def test_a_beekeeper_sees_their_apiaries_and_an_admin_sees_all(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ana = await add_user(engine, "ana@example.com")
    bob = await add_user(engine, "bob@example.com")
    await add_user(engine, "root@example.com", "admin")
    async with engine.begin() as conn:
        for owner, name in ((ana, "A1"), (ana, "A2"), (bob, "B1")):
            await conn.execute(
                text("INSERT INTO apiaries (id, owner_id, name) VALUES (gen_random_uuid(), :o, :n)"),
                {"o": owner, "n": name},
            )

    async def names(email: str) -> list[str]:
        r = await client.get("/api/v1/apiaries", headers=bearer(await login(client, email)))
        assert r.status_code == 200
        return sorted(i["name"] for i in r.json()["items"])

    assert await names("ana@example.com") == ["A1", "A2"]
    assert await names("bob@example.com") == ["B1"]
    assert await names("root@example.com") == ["A1", "A2", "B1"]


async def test_lists_page_with_an_opaque_cursor(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    root = await add_user(engine, "root@example.com", "admin")
    async with engine.begin() as conn:
        for i in range(5):
            await conn.execute(
                text("INSERT INTO apiaries (id, owner_id, name) VALUES (gen_random_uuid(), :o, :n)"),
                {"o": root, "n": f"A{i}"},
            )
    headers = bearer(await login(client, "root@example.com"))
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        params: dict[str, str | int] = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = (await client.get("/api/v1/apiaries", headers=headers, params=params)).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 5
    bad = await client.get("/api/v1/apiaries", headers=headers, params={"cursor": "!!!"})
    assert bad.status_code == 400
    assert (await client.get("/api/v1/apiaries", headers=headers, params={"limit": 0})).status_code == 422


async def test_readiness_is_ok_with_a_database(client: httpx.AsyncClient) -> None:
    assert (await client.get("/readyz")).json() == {"status": "ready"}
