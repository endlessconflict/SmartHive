"""Apiaries, hives and readings through the API: ownership scoping, editing, bucketed series."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.app import create_app
from smarthive.api.security import create_access_token
from smarthive.config import Settings
from tests.integration.test_api_auth import SECRET, add_user

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(jwt_secret=SECRET), engine)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


def auth(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(SECRET, user_id, 'beekeeper', 15)}"}


async def test_create_and_scope_apiaries_and_hives(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ana = await add_user(engine, f"ana-{uuid4().hex[:6]}@example.com")
    bob = await add_user(engine, f"bob-{uuid4().hex[:6]}@example.com")
    admin = await add_user(engine, f"adm-{uuid4().hex[:6]}@example.com", "admin")

    r = await client.post("/api/v1/apiaries", json={"name": "Boquete"}, headers=auth(ana))
    assert r.status_code == 201 and r.json()["owner_id"] == str(ana)
    apiary = r.json()["id"]

    h = await client.post(
        f"/api/v1/apiaries/{apiary}/hives", json={"name": "H1", "boxes": 2}, headers=auth(ana)
    )
    assert h.status_code == 201 and h.json()["archived"] is False
    hive = h.json()["id"]

    # another beekeeper sees nothing, and cannot tell the ids exist
    for path in (f"/api/v1/apiaries/{apiary}", f"/api/v1/apiaries/{apiary}/hives", f"/api/v1/hives/{hive}"):
        assert (await client.get(path, headers=auth(bob))).status_code == 404
    assert (
        await client.post(f"/api/v1/apiaries/{apiary}/hives", json={"name": "x"}, headers=auth(bob))
    ).status_code == 404
    assert (await client.get(f"/api/v1/hives/{hive}", headers=auth(admin))).status_code == 200
    assert (await client.get(f"/api/v1/hives/{hive}")).status_code == 401


async def test_patch_archives_and_hides_from_the_default_list(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ana = await add_user(engine, f"ana-{uuid4().hex[:6]}@example.com")
    apiary = (await client.post("/api/v1/apiaries", json={"name": "A"}, headers=auth(ana))).json()["id"]
    hive = (
        await client.post(
            f"/api/v1/apiaries/{apiary}/hives", json={"name": "H", "notes": "n"}, headers=auth(ana)
        )
    ).json()["id"]

    r = await client.patch(f"/api/v1/hives/{hive}", json={"archived": True, "notes": None}, headers=auth(ana))
    assert r.status_code == 200 and r.json()["archived"] is True and r.json()["notes"] is None
    assert r.json()["name"] == "H"  # untouched

    listing = f"/api/v1/apiaries/{apiary}/hives"
    assert (await client.get(listing, headers=auth(ana))).json()["items"] == []
    assert (
        len((await client.get(listing, params={"include_archived": True}, headers=auth(ana))).json()["items"])
        == 1
    )
    assert (
        await client.patch(f"/api/v1/hives/{hive}", json={"name": None}, headers=auth(ana))
    ).status_code == 422


async def test_readings_raw_bucketed_and_validated(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ana = await add_user(engine, f"ana-{uuid4().hex[:6]}@example.com")
    apiary = (await client.post("/api/v1/apiaries", json={"name": "A"}, headers=auth(ana))).json()["id"]
    hive = (
        await client.post(f"/api/v1/apiaries/{apiary}/hives", json={"name": "H"}, headers=auth(ana))
    ).json()["id"]
    t0 = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=3)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO nodes (id, is_simulated, device_token_hash) "
                "VALUES ('n1', true, 'x') ON CONFLICT DO NOTHING"
            )
        )
        for i, (v, q) in enumerate([(30.0, "ok"), (32.0, "ok"), (99.0, "stuck"), (34.0, "ok")]):
            await conn.execute(
                text(
                    "INSERT INTO readings "
                    "(ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, msg_id, idx) "
                    "VALUES (:ts, 'n1', :h, 'temperature', :v, :q, 's', true, :m, 0)"
                ),
                {"ts": t0 + timedelta(minutes=10 * i), "h": hive, "v": v, "q": q, "m": uuid4()},
            )
    base = f"/api/v1/hives/{hive}/readings"
    raw = (await client.get(base, params={"quantity": "temperature"}, headers=auth(ana))).json()
    assert [p["value"] for p in raw["points"]] == [30.0, 32.0, 34.0]  # the stuck one is dropped
    hourly = (
        await client.get(base, params={"quantity": "temperature", "bucket": "1h"}, headers=auth(ana))
    ).json()
    assert len(hourly["points"]) == 1 and hourly["points"][0]["n"] == 3
    assert hourly["points"][0]["value"] == pytest.approx(32.0) and hourly["points"][0]["max"] == 34.0

    bad = await client.get(
        base, params={"quantity": "temperature", "start": "2026-01-01T00:00:00"}, headers=auth(ana)
    )
    assert bad.status_code == 422  # no timezone offset
    assert (
        await client.get(base, params={"quantity": "t", "bucket": "2s"}, headers=auth(ana))
    ).status_code == 422
