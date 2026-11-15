"""US11.3: the in-app inbox, and the preferences behind the notification channels (PATCH /me)."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.alerts.engine import evaluate_all
from smarthive.api.app import create_app
from smarthive.config import Settings
from tests.integration.test_alerts import add_hornet, auth, setup_hive
from tests.integration.test_api_auth import SECRET

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(jwt_secret=SECRET), engine)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


async def test_inbox_lists_marks_read_and_counts(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    await add_hornet(engine, hive, node)
    await evaluate_all(engine)
    h = auth(owner)

    page = (await client.get("/api/v1/me/notifications", headers=h)).json()
    assert page["unread"] == 1 and len(page["items"]) == 1  # the email row is not an inbox item
    item = page["items"][0]
    assert item["severity"] == "critical" and item["title"] == "Hornet at the entrance"
    assert item["hive_id"] == str(hive) and item["read_at"] is None

    r = await client.post(f"/api/v1/me/notifications/{item['id']}/read", headers=h)
    assert r.status_code == 204
    page = (await client.get("/api/v1/me/notifications", headers=h)).json()
    assert page["unread"] == 0 and page["items"][0]["read_at"] is not None
    assert (await client.get("/api/v1/me/notifications?unread=true", headers=h)).json()["items"] == []


async def test_inbox_is_private_and_read_all_works(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    stranger, *_ = await setup_hive(engine)
    await add_hornet(engine, hive, node)
    await evaluate_all(engine)

    assert (await client.get("/api/v1/me/notifications", headers=auth(stranger))).json()["items"] == []
    own = (await client.get("/api/v1/me/notifications", headers=auth(owner))).json()["items"][0]["id"]
    assert (
        await client.post(f"/api/v1/me/notifications/{own}/read", headers=auth(stranger))
    ).status_code == 404

    assert (await client.post("/api/v1/me/notifications/read-all", headers=auth(owner))).status_code == 204
    assert (await client.get("/api/v1/me/notifications", headers=auth(owner))).json()["unread"] == 0


async def test_inbox_pages_by_cursor(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    for _ in range(3):  # three episodes, three alerts
        await add_hornet(engine, hive, node)
    await evaluate_all(engine)
    h = auth(owner)
    first = (await client.get("/api/v1/me/notifications?limit=2", headers=h)).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = (
        await client.get(f"/api/v1/me/notifications?limit=2&cursor={first['next_cursor']}", headers=h)
    ).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert (await client.get("/api/v1/me/notifications?cursor=%21%21", headers=h)).status_code == 400


async def test_patch_me_changes_only_what_is_sent(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, *_ = await setup_hive(engine)
    h = auth(owner)
    r = await client.patch(
        "/api/v1/me", json={"ntfy_topic": "smarthive-demo", "notify_email": False}, headers=h
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ntfy_topic"] == "smarthive-demo" and body["notify_email"] is False
    name = body["display_name"]

    r = await client.patch("/api/v1/me", json={"ntfy_topic": ""}, headers=h)
    assert r.json()["ntfy_topic"] is None and r.json()["display_name"] == name
    assert (await client.get("/api/v1/me", headers=h)).json()["notify_email"] is False

    assert (await client.patch("/api/v1/me", json={"display_name": None}, headers=h)).status_code == 422
    assert (await client.patch("/api/v1/me", json={"role": "admin"}, headers=h)).json()["role"] == "beekeeper"
