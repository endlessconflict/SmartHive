"""The beekeeper log, anomalies and predictions, the ML job interface, and the disturbance mask."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive import jobs
from smarthive.alerts.engine import evaluate_all
from smarthive.api.app import create_app
from smarthive.config import Settings
from tests.integration.test_alerts import alerts_of, auth, setup_hive
from tests.integration.test_api_auth import SECRET, add_user

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(jwt_secret=SECRET), engine)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


async def add_readings(
    engine: AsyncEngine, hive: UUID, node: str, minutes_ago: list[int], value: float, now: datetime
) -> None:
    async with engine.begin() as c:
        for m in minutes_ago:
            await c.execute(
                text(
                    "INSERT INTO readings (ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, msg_id, idx) "
                    "VALUES (:t, :n, :h, 'temp_in', :v, 'ok', 's', true, :m, 0)"
                ),
                {"t": now - timedelta(minutes=m), "n": node, "h": hive, "v": value, "m": uuid4()},
            )


async def test_log_list_and_scope_management_events(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, _ = await setup_hive(engine)
    other = await add_user(engine, f"x-{uuid4().hex[:6]}@example.com")
    url = f"/api/v1/hives/{hive}/management-events"
    start = datetime.now(UTC) - timedelta(hours=2)

    made = await client.post(
        url,
        json={"type": "harvest", "started_at": start.isoformat(), "data": {"harvest_kg": 8.5}},
        headers=auth(owner),
    )
    assert made.status_code == 201 and made.json()["data"] == {"harvest_kg": 8.5}
    assert made.json()["created_by"] == str(owner)

    listed = (await client.get(url, headers=auth(owner))).json()
    assert [e["type"] for e in listed] == ["harvest"] and listed[0]["data"]["harvest_kg"] == 8.5
    assert (await client.get(url, headers=auth(other))).status_code == 404
    assert (
        await client.post(url, json={"type": "harvest", "started_at": start.isoformat()}, headers=auth(other))
    ).status_code == 404


async def test_a_bad_event_is_refused(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, _ = await setup_hive(engine)
    url = f"/api/v1/hives/{hive}/management-events"
    now = datetime.now(UTC)
    ends_first = {
        "type": "inspection",
        "started_at": now.isoformat(),
        "ended_at": (now - timedelta(hours=1)).isoformat(),
    }
    assert (await client.post(url, json=ends_first, headers=auth(owner))).status_code == 422
    unknown = {"type": "dance", "started_at": now.isoformat()}
    assert (await client.post(url, json=unknown, headers=auth(owner))).status_code == 422
    naive = {"type": "inspection", "started_at": "2026-10-01T10:00:00"}
    assert (await client.post(url, json=naive, headers=auth(owner))).status_code == 422


async def test_a_job_writes_and_the_api_reads_anomalies_and_the_latest_prediction(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, hive, _ = await setup_hive(engine)
    now = datetime.now(UTC)
    await jobs.write_anomaly(
        engine, hive, now - timedelta(hours=3), now - timedelta(hours=2), 0.91, "iforest-v1", "swarming"
    )
    await jobs.write_anomaly(engine, hive, now - timedelta(hours=1), now, 0.55, "iforest-v1")
    old, new = now - timedelta(days=1), now
    await jobs.write_prediction(engine, hive, "yield_7d_kg", timedelta(days=7), 1.0, 2.0, 3.0, "gbm-v1", old)
    await jobs.write_prediction(engine, hive, "yield_7d_kg", timedelta(days=7), 2.0, 3.5, 5.0, "gbm-v2", new)

    anomalies = (await client.get(f"/api/v1/hives/{hive}/anomalies", headers=auth(owner))).json()
    assert [a["score"] for a in anomalies] == pytest.approx([0.55, 0.91])  # newest first
    assert anomalies[0]["kind"] is None and anomalies[1]["kind"] == "swarming"
    assert {a["model"] for a in anomalies} == {"iforest-v1"}

    (pred,) = (
        await client.get(f"/api/v1/hives/{hive}/predictions?target=yield_7d_kg", headers=auth(owner))
    ).json()
    assert (pred["p10"], pred["p50"], pred["p90"], pred["model"]) == (2.0, 3.5, 5.0, "gbm-v2")
    assert pred["horizon_s"] == 7 * 86400
    assert (
        await client.get(f"/api/v1/hives/{hive}/predictions?target=nothing", headers=auth(owner))
    ).json() == []


async def test_a_job_must_name_its_model_and_give_an_ordered_range(engine: AsyncEngine) -> None:
    _, hive, _ = await setup_hive(engine)
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        await jobs.write_anomaly(engine, hive, now - timedelta(hours=1), now, 0.5, "")
    with pytest.raises(ValueError):
        await jobs.write_prediction(engine, hive, "yield_7d_kg", timedelta(days=7), 3.0, 2.0, 1.0, "m")


async def test_features_leave_out_a_management_event_and_its_margin(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    await add_readings(engine, hive, node, [300, 240, 200, 100], 35.0, now)
    async with engine.begin() as c:  # inspection from 210 to 190 minutes ago, plus the 30 minute margin
        await c.execute(
            text(
                "INSERT INTO management_events (id, hive_id, type, started_at, ended_at) "
                "VALUES (:i, :h, 'inspection', :s, :e)"
            ),
            {"i": uuid4(), "h": hive, "s": now - timedelta(minutes=210), "e": now - timedelta(minutes=190)},
        )
    features = await jobs.read_features(engine, hive, now - timedelta(hours=6), now, timedelta(minutes=1))
    kept = sorted(int((now - f.ts).total_seconds() // 60) for f in features)
    assert kept == [100, 240, 300]  # 200 is inside the event, 240 is outside the margin


async def test_a_logged_inspection_keeps_the_temperature_rule_quiet(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine)
    now = datetime.now(UTC)
    await add_readings(engine, hive, node, [5, 60, 100, 118], 41.0, now)  # hot across the whole window
    async with engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO management_events (id, hive_id, type, started_at, ended_at) "
                "VALUES (:i, :h, 'inspection', :s, :e)"
            ),
            {"i": uuid4(), "h": hive, "s": now - timedelta(minutes=20), "e": now - timedelta(minutes=10)},
        )
    await evaluate_all(engine, now)
    assert [a.rule_id for a in await alerts_of(engine, hive)] == []  # inside the event's 30 minute margin
    async with engine.begin() as c:
        await c.execute(text("DELETE FROM management_events"))
    await evaluate_all(engine, now)
    assert [a.rule_id for a in await alerts_of(engine, hive)] == ["temp_out_of_range"]
