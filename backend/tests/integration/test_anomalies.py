"""US17: anomalies found in stored readings, as warning windows in the API, with no notification at all."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive import jobs
from smarthive.alerts.engine import evaluate_all
from smarthive.api.app import create_app
from smarthive.config import Settings
from smarthive.demo import write_history
from tests.integration.test_alerts import auth, setup_hive
from tests.integration.test_api_auth import SECRET, add_user

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(jwt_secret=SECRET), engine)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


async def warnings(engine: AsyncEngine, hive: UUID) -> list[tuple[str, str, str]]:
    """(severity, state, quantity) of the hive's anomaly alerts, oldest first."""
    async with engine.connect() as c:
        rows = await c.execute(
            text(
                "SELECT severity, state, details ->> 'quantity' AS q FROM alerts "
                "WHERE hive_id = :h AND rule_id = 'anomaly_detected' ORDER BY opened_at"
            ),
            {"h": hive},
        )
        return [(r.severity, r.state, r.q) for r in rows]


async def notifications(engine: AsyncEngine, hive: UUID) -> int:
    async with engine.connect() as c:
        n = await c.execute(
            text(
                "SELECT count(*) FROM notifications n JOIN alerts a ON a.id = n.alert_id "
                "WHERE a.hive_id = :h AND a.rule_id = 'anomaly_detected'"
            ),
            {"h": hive},
        )
        return int(n.scalar_one())


async def windows(client: httpx.AsyncClient, hive: UUID, owner: UUID, **params: str) -> httpx.Response:
    return await client.get(f"/api/v1/hives/{hive}/anomalies", params=params, headers=auth(owner))


async def test_an_anomaly_is_a_warning_window_and_nobody_is_notified(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, hive, node = await setup_hive(engine, simulated=True)
    await write_history(engine, node, "rh_in", days=3, hours=4, now=NOW, seed=1)
    await evaluate_all(engine, NOW)

    assert await warnings(engine, hive) == [("warning", "open", "rh_in")]
    assert await notifications(engine, hive) == 0  # not even in-app

    [w] = (await windows(client, hive, owner)).json()
    assert (w["kind"], w["model"], w["level"]) == ("rh_in_low", "robust-z@1", "warning")
    assert w["score"] >= 6
    start, end = datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"])
    assert NOW - timedelta(hours=5) <= start <= NOW - timedelta(hours=3)
    assert NOW < end <= NOW + timedelta(hours=1)

    [alert] = (await client.get("/api/v1/alerts", params={"hive_id": str(hive)}, headers=auth(owner))).json()[
        "items"
    ]
    assert alert["title"] == "Very unusually low humidity"
    d = alert["details"]
    assert d["anomaly_id"] == w["id"] and d["value"] < 50 < d["expected"] and d["unit"] == "%"

    status = (await client.get(f"/api/v1/hives/{hive}/latest", headers=auth(owner))).json()
    assert (status["open_alerts"], status["open_anomalies"]) == (0, 1)  # not an alert to act on

    later = (NOW + timedelta(hours=2)).isoformat()
    assert (
        await windows(client, hive, owner, start=later, end=(NOW + timedelta(hours=3)).isoformat())
    ).json() == []
    stranger = await add_user(engine, f"s-{node}@example.com")
    assert (await windows(client, hive, stranger)).status_code == 404


async def test_the_window_grows_instead_of_repeating(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine, simulated=True)
    await write_history(engine, node, "temp_in", shift=1.2, days=3, hours=4, now=NOW, seed=2)
    await evaluate_all(engine, NOW - timedelta(hours=1))
    await evaluate_all(engine, NOW)
    async with engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT lower(period) AS s, upper(period) AS e, level FROM anomalies WHERE hive_id = :h"
                ),
                {"h": hive},
            )
        ).all()
    assert len(rows) == 1 and rows[0].level == "info"
    assert rows[0].e > NOW  # extended by the second evaluation


async def test_the_warning_closes_by_itself_and_the_band_stays(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, hive, node = await setup_hive(engine, simulated=True)
    await write_history(engine, node, "temp_in", shift=1.2, days=3, hours=4, now=NOW, seed=2)
    await evaluate_all(engine, NOW)
    assert await warnings(engine, hive) == [("info", "open", "temp_in")]
    [w] = (await windows(client, hive, owner)).json()

    later = NOW + timedelta(hours=6)  # the same days of readings, then six normal hours
    async with engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO readings (ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, "
                "msg_id, idx) SELECT t, :n, :h, 'temp_in', 35.0, 'ok', 'dht11-0', true, gen_random_uuid(), 0 "
                "FROM generate_series(CAST(:a AS timestamptz), CAST(:b AS timestamptz), interval '5 minutes') t"
            ),
            {"n": node, "h": hive, "a": NOW + timedelta(minutes=5), "b": later},
        )
    await evaluate_all(engine, later)
    assert await warnings(engine, hive) == [("info", "resolved", "temp_in")]
    assert [x["id"] for x in (await windows(client, hive, owner)).json()] == [w["id"]]  # a past band


async def test_growing_to_warning_notifies_nobody_either(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine, simulated=True)
    await write_history(engine, node, "temp_in", shift=1.2, days=3, hours=4, now=NOW, seed=2)
    await evaluate_all(engine, NOW)
    assert await warnings(engine, hive) == [("info", "open", "temp_in")]
    await write_history(engine, node, "temp_in", shift=2.2, days=3, hours=4, now=NOW, seed=2)
    await evaluate_all(engine, NOW)
    assert await warnings(engine, hive) == [("warning", "open", "temp_in")]
    assert await notifications(engine, hive) == 0
    async with engine.connect() as c:
        kinds = (
            await c.execute(
                text(
                    "SELECT e.kind FROM alert_events e JOIN alerts a ON a.id = e.alert_id "
                    "WHERE a.hive_id = :h ORDER BY e.id"
                ),
                {"h": hive},
            )
        ).scalars()
        assert list(kinds) == ["opened", "escalated"]


async def test_a_short_history_gives_no_anomaly(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine, simulated=True)
    await write_history(engine, node, "temp_in", shift=3, days=1.5, hours=4, now=NOW, seed=5)
    await evaluate_all(engine, NOW)
    assert await warnings(engine, hive) == []


async def test_an_ml_window_carries_its_level_and_is_never_critical(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, hive, _ = await setup_hive(engine)
    await jobs.write_anomaly(engine, hive, NOW - timedelta(hours=2), NOW, 0.7, "iforest-v1", level="info")
    [w] = (await windows(client, hive, owner)).json()
    assert (w["level"], w["kind"]) == ("info", None)
    with pytest.raises(ValueError, match="level"):
        await jobs.write_anomaly(
            engine, hive, NOW - timedelta(hours=2), NOW, 0.9, "iforest-v1", level="critical"
        )


async def test_demo_data_for_a_real_node_needs_to_be_asked_for(engine: AsyncEngine) -> None:
    _, hive, node = await setup_hive(engine, simulated=False)
    with pytest.raises(SystemExit, match="--real-node"):
        await write_history(engine, node, "temp_in", now=NOW)
    done = await write_history(engine, node, "temp_in", now=NOW, real_node=True)
    assert done["hive_id"] == hive and done["readings"] > 0
