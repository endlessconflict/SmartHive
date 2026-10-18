"""Rules, alert lifecycle, notifications and the alert API, against a real database."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.alerts.engine import evaluate_all
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


def auth(user_id: UUID, role: str = "beekeeper") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(SECRET, user_id, role, 15)}"}


async def setup_hive(engine: AsyncEngine, simulated: bool = False) -> tuple[UUID, UUID, str]:
    """An owner with one hive and one node assigned to it: (owner, hive, node)."""
    owner = await add_user(engine, f"o-{uuid4().hex[:8]}@example.com")
    hive, apiary, node = uuid4(), uuid4(), f"n-{uuid4().hex[:8]}"
    async with engine.begin() as c:
        await c.execute(text("UPDATE users SET notify_email = true WHERE id = :u"), {"u": owner})
        await c.execute(
            text("INSERT INTO apiaries (id, owner_id, name) VALUES (:a, :o, 'A')"), {"a": apiary, "o": owner}
        )
        await c.execute(
            text("INSERT INTO hives (id, apiary_id, name) VALUES (:h, :a, 'H')"), {"h": hive, "a": apiary}
        )
        await c.execute(
            text(
                "INSERT INTO nodes (id, is_simulated, device_token_hash, last_seen_at, status) "
                "VALUES (:n, :s, 'x', now(), 'online')"
            ),
            {"n": node, "s": simulated},
        )
        await c.execute(
            text(
                "INSERT INTO node_assignments (node_id, hive_id, valid) VALUES (:n, :h, tstzrange(now() - interval '30 days', NULL))"
            ),
            {"n": node, "h": hive},
        )
    return owner, hive, node


async def alerts_of(engine: AsyncEngine, hive: UUID) -> list[Row[Any]]:
    async with engine.connect() as c:
        return list(
            (
                await c.execute(
                    text("SELECT * FROM alerts WHERE hive_id = :h ORDER BY opened_at"), {"h": hive}
                )
            ).all()
        )


async def add_hornet(engine: AsyncEngine, hive: UUID, node: str) -> None:
    now = datetime.now(UTC)
    async with engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO detection_events (msg_id, episode_id, node_id, hive_id, type, cls, first_seen, last_seen, max_conf) "
                "VALUES (:m, :e, :n, :h, 'threat_detected', 'hornet', :t, :t, 0.93)"
            ),
            {"m": uuid4(), "e": uuid4(), "n": node, "h": hive, "t": now},
        )


async def test_hornet_opens_one_critical_alert_and_notifies_the_owner(engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    await add_hornet(engine, hive, node)
    await evaluate_all(engine)
    await evaluate_all(engine)  # the same episode again: no second alert
    (alert,) = await alerts_of(engine, hive)
    assert alert.severity == "critical" and alert.state == "open" and alert.rule_id == "hornet_detected"
    async with engine.connect() as c:
        channels = {
            r.channel: r.status
            for r in await c.execute(
                text("SELECT channel, status FROM notifications WHERE alert_id = :a"), {"a": alert.id}
            )
        }
    assert channels == {"app": "sent", "email": "pending"}


async def test_simulated_nodes_never_get_email(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine, simulated=True)
    await add_hornet(engine, hive, node)
    await evaluate_all(engine)
    (alert,) = await alerts_of(engine, hive)
    async with engine.connect() as c:
        rows = (
            await c.execute(text("SELECT channel FROM notifications WHERE alert_id = :a"), {"a": alert.id})
        ).all()
    assert [r.channel for r in rows] == ["app"]


async def test_a_resolved_episode_does_not_come_back(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    await add_hornet(engine, hive, node)
    await evaluate_all(engine)
    (alert,) = await alerts_of(engine, hive)
    r = await client.post(
        f"/api/v1/alerts/{alert.id}/resolve", json={"note": "closed the entrance"}, headers=auth(owner)
    )
    assert r.status_code == 200 and r.json()["state"] == "resolved"
    await evaluate_all(engine)
    assert len(await alerts_of(engine, hive)) == 1


async def test_temperature_out_of_range_needs_the_whole_window(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine)
    now = datetime.now(UTC)

    async def readings(minutes_ago: list[int], value: float) -> None:
        async with engine.begin() as c:
            for m in minutes_ago:
                await c.execute(
                    text(
                        "INSERT INTO readings (ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, msg_id, idx) "
                        "VALUES (:t, :n, :h, 'temp_in', :v, 'ok', 's', true, :m, 0)"
                    ),
                    {"t": now - timedelta(minutes=m), "n": node, "h": hive, "v": value, "m": uuid4()},
                )

    await readings([5, 20], 41.0)  # hot, but only for 20 minutes
    await evaluate_all(engine, now)
    assert await alerts_of(engine, hive) == []
    await readings([60, 100, 118], 41.0)  # hot across the 2 h window
    await evaluate_all(engine, now)
    (alert,) = await alerts_of(engine, hive)
    assert alert.rule_id == "temp_out_of_range" and alert.severity == "warning"


async def test_node_offline_resolves_itself(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine)
    async with engine.begin() as c:
        await c.execute(
            text("UPDATE nodes SET last_seen_at = now() - interval '1 hour' WHERE id = :n"), {"n": node}
        )
    await evaluate_all(engine)
    (alert,) = await alerts_of(engine, hive)
    assert alert.rule_id == "node_offline" and alert.state == "open"
    async with engine.begin() as c:
        await c.execute(text("UPDATE nodes SET last_seen_at = now() WHERE id = :n"), {"n": node})
    await evaluate_all(engine)
    (alert,) = await alerts_of(engine, hive)
    assert alert.state == "resolved" and alert.resolved_by is None


async def test_lifecycle_and_visibility_through_the_api(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, hive, node = await setup_hive(engine)
    other = await add_user(engine, f"x-{uuid4().hex[:8]}@example.com")
    await add_hornet(engine, hive, node)
    await evaluate_all(engine)
    (alert,) = await alerts_of(engine, hive)
    path = f"/api/v1/alerts/{alert.id}"

    listed = await client.get("/api/v1/alerts", params={"hive_id": str(hive)}, headers=auth(owner))
    assert [a["id"] for a in listed.json()["items"]] == [str(alert.id)]
    assert (await client.get(path, headers=auth(other))).status_code == 404  # not theirs
    assert (await client.get("/api/v1/alerts", params={"hive_id": str(hive)}, headers=auth(other))).json()[
        "items"
    ] == []

    assert (await client.post(f"{path}/acknowledge", headers=auth(owner))).json()["state"] == "acknowledged"
    assert (await client.post(f"{path}/acknowledge", headers=auth(owner))).status_code == 409
    assert (await client.post(f"{path}/resolve", json={}, headers=auth(owner))).json()["state"] == "resolved"
    assert (await client.post(f"{path}/resolve", json={}, headers=auth(owner))).status_code == 409
    kinds = [e["kind"] for e in (await client.get(path, headers=auth(owner))).json()["events"]]
    assert kinds == ["opened", "acknowledged", "resolved"]


async def test_page_through_alerts(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    for _ in range(3):
        await add_hornet(engine, hive, node)
    await evaluate_all(engine)
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, str | int] = {"hive_id": str(hive), "limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = (await client.get("/api/v1/alerts", params=params, headers=auth(owner))).json()
        seen += [a["id"] for a in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 3


async def test_only_admins_adjust_rules_and_values_are_checked(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, _, _ = await setup_hive(engine)
    admin = await add_user(engine, f"a-{uuid4().hex[:8]}@example.com", "admin")
    rules = (await client.get("/api/v1/alert-rules", headers=auth(owner))).json()
    assert {"hornet_detected", "temp_out_of_range"} <= {r["id"] for r in rules}
    url = "/api/v1/alert-rules/temp_out_of_range"
    assert (await client.patch(url, json={"enabled": False}, headers=auth(owner))).status_code == 403
    ok = await client.patch(url, json={"params": {"high": 38}}, headers=auth(admin, "admin"))
    assert ok.status_code == 200 and ok.json()["params"]["high"] == 38 and ok.json()["params"]["low"] == 32
    assert (
        await client.patch(url, json={"params": {"hihg": 38}}, headers=auth(admin, "admin"))
    ).status_code == 422
    assert (
        await client.patch(url, json={"params": {"high": "hot"}}, headers=auth(admin, "admin"))
    ).status_code == 422
    assert (
        await client.patch("/api/v1/alert-rules/nope", json={}, headers=auth(admin, "admin"))
    ).status_code == 404
    await client.patch(
        url, json={"params": {"high": 37}}, headers=auth(admin, "admin")
    )  # restore the default


async def test_the_worker_wakes_on_notify(engine: AsyncEngine) -> None:
    from smarthive.alerts.engine import run
    from smarthive.ingest.handler import CHANNEL

    url = engine.url.render_as_string(hide_password=False)
    stop = asyncio.Event()
    worker = asyncio.create_task(run(Settings(db_url=url, alert_interval_s=3600), stop))
    try:
        await asyncio.sleep(1)  # first pass done, now it sleeps for an hour unless woken
        _, hive, node = await setup_hive(engine)
        await add_hornet(engine, hive, node)
        async with engine.begin() as c:
            await c.execute(text("SELECT pg_notify(:ch, '{}')"), {"ch": CHANNEL})
        for _ in range(40):
            if await alerts_of(engine, hive):
                break
            await asyncio.sleep(0.25)
        assert len(await alerts_of(engine, hive)) == 1
    finally:
        stop.set()
        await asyncio.wait_for(worker, 5)
