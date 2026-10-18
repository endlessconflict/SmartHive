"""Node registration, assignment with back-fill, and the live hive overview."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.app import create_app
from smarthive.api.security import create_access_token, hash_refresh_token
from smarthive.config import Settings
from tests.integration.test_api_auth import SECRET, add_user

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(jwt_secret=SECRET), engine)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


def auth(user_id: UUID, role: str = "beekeeper") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(SECRET, user_id, role, 15)}"}


def admin_auth(user_id: UUID) -> dict[str, str]:
    return auth(user_id, "admin")


async def make_hive(client: httpx.AsyncClient, owner: UUID, name: str = "H") -> str:
    apiary = (await client.post("/api/v1/apiaries", json={"name": "A"}, headers=auth(owner))).json()["id"]
    r = await client.post(f"/api/v1/apiaries/{apiary}/hives", json={"name": name}, headers=auth(owner))
    return str(r.json()["id"])


async def add_reading(
    engine: AsyncEngine, node: str, hive: str | None, quantity: str, value: float, ts: datetime
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO nodes (id, is_simulated) VALUES (:n, :s) ON CONFLICT DO NOTHING"),
            {"n": node, "s": node.startswith("sim-")},
        )
        await conn.execute(
            text(
                "INSERT INTO readings (ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, "
                "msg_id, idx) VALUES (:ts, :n, :h, :q, :v, 'ok', 's', true, :m, 0)"
            ),
            {"ts": ts, "n": node, "h": hive, "q": quantity, "v": value, "m": uuid4()},
        )


def email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:6]}@example.com"


async def test_register_issues_the_token_once(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ana = await add_user(engine, email("ana"))
    adm = await add_user(engine, email("adm"), "admin")
    node = f"hive-{uuid4().hex[:6]}"

    assert (await client.post("/api/v1/nodes", json={"id": node}, headers=auth(ana))).status_code == 403
    assert (
        await client.post("/api/v1/nodes", json={"id": "Bad Id"}, headers=admin_auth(adm))
    ).status_code == 422

    r = await client.post("/api/v1/nodes", json={"id": node}, headers=admin_auth(adm))
    assert r.status_code == 201 and r.json()["simulated"] is False and r.json()["has_token"] is True
    token = r.json()["device_token"]
    async with engine.connect() as conn:
        stored = (
            await conn.execute(text("SELECT device_token_hash FROM nodes WHERE id = :i"), {"i": node})
        ).scalar()
    assert stored == hash_refresh_token(token) != token

    assert (await client.post("/api/v1/nodes", json={"id": node}, headers=admin_auth(adm))).status_code == 409
    sim = await client.post("/api/v1/nodes", json={"id": "sim-01"}, headers=admin_auth(adm))
    assert sim.json()["simulated"] is True


async def test_register_adopts_a_node_that_spoke_mqtt_first(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    adm = await add_user(engine, email("adm"), "admin")
    node = f"hive-{uuid4().hex[:6]}"
    await add_reading(engine, node, None, "temp_c", 20, datetime.now(UTC))
    r = await client.post("/api/v1/nodes", json={"id": node}, headers=admin_auth(adm))
    assert r.status_code == 201


async def test_assign_backfills_and_rejects_overlap(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ana = await add_user(engine, email("ana"))
    adm = await add_user(engine, email("adm"), "admin")
    h1, h2 = await make_hive(client, ana, "H1"), await make_hive(client, ana, "H2")
    node = f"hive-{uuid4().hex[:6]}"
    now = datetime.now(UTC)
    await add_reading(engine, node, None, "temp_c", 33, now - timedelta(hours=1))
    await add_reading(engine, node, None, "temp_c", 20, now - timedelta(days=3))

    url = f"/api/v1/nodes/{node}/assign"
    assert (await client.post(url, json={"hive_id": h1}, headers=auth(ana))).status_code == 403
    assert (
        await client.post(url, json={"hive_id": str(uuid4())}, headers=admin_auth(adm))
    ).status_code == 404
    missing = await client.post("/api/v1/nodes/nope/assign", json={"hive_id": h1}, headers=admin_auth(adm))
    assert missing.status_code == 404

    since = (now - timedelta(days=1)).isoformat()
    r = await client.post(url, json={"hive_id": h1, "valid_from": since}, headers=admin_auth(adm))
    assert r.status_code == 200 and r.json()["hive_id"] == h1
    async with engine.connect() as conn:
        got = (
            await conn.execute(
                text("SELECT value, hive_id FROM readings WHERE node_id = :n ORDER BY ts"), {"n": node}
            )
        ).all()
    assert [(g.value, g.hive_id and str(g.hive_id)) for g in got] == [
        (20, None),
        (33, h1),
    ]  # only after valid_from

    assert (await client.post(url, json={"hive_id": h2}, headers=admin_auth(adm))).status_code == 409

    off = await client.post(f"/api/v1/nodes/{node}/unassign", headers=admin_auth(adm))
    assert off.status_code == 200 and off.json()["hive_id"] is None
    assert (await client.post(f"/api/v1/nodes/{node}/unassign", headers=admin_auth(adm))).status_code == 409
    assert (await client.post(url, json={"hive_id": h2}, headers=admin_auth(adm))).status_code == 200


async def test_hive_overview_has_latest_alerts_node_and_simulated(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ana = await add_user(engine, email("ana"))
    bob = await add_user(engine, email("bob"))
    adm = await add_user(engine, email("adm"), "admin")
    hive, bare = await make_hive(client, ana, "H1"), await make_hive(client, ana, "H2")
    node = f"sim-{uuid4().hex[:6]}"
    now = datetime.now(UTC)
    await add_reading(engine, node, hive, "temp_c", 30, now - timedelta(minutes=5))
    await add_reading(engine, node, hive, "temp_c", 34, now - timedelta(minutes=1))
    await add_reading(engine, node, hive, "rh_pct", 60, now - timedelta(minutes=2))
    await client.post(f"/api/v1/nodes/{node}/assign", json={"hive_id": hive}, headers=admin_auth(adm))
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO alerts (id, hive_id, rule_id, severity, state, title, details, dedup_key, "
                "opened_at, last_seen_at) VALUES (:i, :h, 'x', 'warning', 'open', 't', '{}', :k, now(), now())"
            ),
            {"i": uuid4(), "h": hive, "k": uuid4().hex},
        )

    items = {i["id"]: i for i in (await client.get("/api/v1/hives", headers=auth(ana))).json()["items"]}
    assert set(items) == {hive, bare}
    h = items[hive]
    assert h["latest"]["temp_c"]["value"] == 34 and h["latest"]["rh_pct"]["value"] == 60
    assert h["open_alerts"] == 1 and h["node_id"] == node and h["simulated"] is True
    assert (
        items[bare]["node_id"] is None and items[bare]["latest"] == {} and items[bare]["simulated"] is False
    )

    assert (await client.get("/api/v1/hives", headers=auth(bob))).json()["items"] == []
    one = await client.get(f"/api/v1/hives/{hive}/latest", headers=auth(ana))
    assert one.status_code == 200 and one.json()["latest"]["temp_c"]["value"] == 34
    assert (await client.get(f"/api/v1/hives/{hive}/latest", headers=auth(bob))).status_code == 404

    page = (await client.get("/api/v1/hives", params={"limit": 1}, headers=auth(ana))).json()
    assert len(page["items"]) == 1 and page["next_cursor"]
