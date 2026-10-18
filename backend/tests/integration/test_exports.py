"""CSV and JSON Lines exports, the simulated/real split, and the Open-Meteo refresh."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive import weather
from smarthive.api.app import create_app
from smarthive.config import Settings
from tests.integration.test_alerts import auth, setup_hive
from tests.integration.test_api_auth import SECRET, add_user

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(jwt_secret=SECRET), engine)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


async def add_node_data(engine: AsyncEngine, hive: UUID, node: str, simulated: bool, now: datetime) -> None:
    async with engine.begin() as c:
        await c.execute(text("UPDATE nodes SET is_simulated = :s WHERE id = :n"), {"s": simulated, "n": node})
        for m, v, q in ((10, 35.0, "ok"), (5, None, "read_error")):
            await c.execute(
                text(
                    "INSERT INTO readings (ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, msg_id, idx) "
                    "VALUES (:t, :n, :h, 'temp_in', :v, :q, 's', true, :m, 0)"
                ),
                {"t": now - timedelta(minutes=m), "n": node, "h": hive, "v": v, "q": q, "m": uuid4()},
            )
        await c.execute(
            text(
                "INSERT INTO detection_events (msg_id, episode_id, node_id, hive_id, type, cls, first_seen, last_seen) "
                "VALUES (:m, :m, :n, :h, 'threat_detected', 'hornet', :t, :t)"
            ),
            {"m": uuid4(), "n": node, "h": hive, "t": now - timedelta(minutes=3)},
        )


async def test_readings_csv_has_a_header_comment_and_keeps_bad_samples(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, hive, node = await setup_hive(engine)
    await add_node_data(engine, hive, node, False, datetime.now(UTC))
    r = await client.get(f"/api/v1/exports/readings?hive_id={hive}", headers=auth(owner))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.splitlines()
    comments = [x for x in lines if x.startswith("# ")]
    assert (
        f"# hive_id: {hive}" in comments and f"# nodes: {node}" in comments and "# simulated: no" in comments
    )
    table = [x for x in lines if not x.startswith("# ")]
    assert table[0] == "ts,node_id,quantity,value,quality,clock_synced"
    assert len(table) == 3 and table[1].split(",")[4] == "ok" and table[2].split(",")[4] == "read_error"


async def test_simulated_data_is_left_out_unless_asked_for(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, hive, node = await setup_hive(engine, simulated=True)
    await add_node_data(engine, hive, node, True, datetime.now(UTC))
    url = f"/api/v1/exports/readings?hive_id={hive}"
    plain = await client.get(url, headers=auth(owner))
    assert "# nodes: none" in plain.text and "temp_in" not in plain.text
    asked = await client.get(url + "&include_simulated=true", headers=auth(owner))
    assert "# simulated: yes" in asked.text and "temp_in" in asked.text


async def test_jsonl_detections_and_quantity_filter(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    await add_node_data(engine, hive, node, False, datetime.now(UTC))
    r = await client.get(f"/api/v1/exports/detections?hive_id={hive}&format=jsonl", headers=auth(owner))
    first, second = (json.loads(x) for x in r.text.splitlines())
    assert first["meta"]["simulated"] == "no" and second["cls"] == "hornet"
    none = await client.get(f"/api/v1/exports/readings?hive_id={hive}&quantity=weight", headers=auth(owner))
    assert [x for x in none.text.splitlines() if not x.startswith("# ")] == []


async def test_exports_follow_hive_ownership(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    _, hive, _ = await setup_hive(engine)
    other = await add_user(engine, f"x-{uuid4().hex[:6]}@example.com")
    assert (
        await client.get(f"/api/v1/exports/readings?hive_id={hive}", headers=auth(other))
    ).status_code == 404
    assert (await client.get(f"/api/v1/exports/readings?hive_id={hive}")).status_code == 401


OPEN_METEO = {
    "hourly": {
        "time": ["2026-10-18T10:00", "2026-10-18T11:00"],
        "temperature_2m": [24.5, 26.0],
        "relative_humidity_2m": [80, 70],
        "precipitation": [0.0, 1.2],
        "wind_speed_10m": [2.5, 3.0],
        "shortwave_radiation": [300, 450],
    }
}


async def test_weather_is_stored_per_apiary_and_served_for_overlays(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    owner, hive, _ = await setup_hive(engine)
    async with engine.begin() as c:
        await c.execute(text("UPDATE apiaries SET lat = 8.78, lon = -82.43"))
    calls: list[tuple[float, float]] = []

    async def fake(lat: float, lon: float) -> dict[str, Any]:
        calls.append((lat, lon))
        return OPEN_METEO

    assert await weather.refresh_all(engine, fake) == 2
    assert await weather.refresh_all(engine, fake) == 2  # a second run updates, it does not duplicate
    assert calls == [(8.78, -82.43)] * 2
    r = await client.get(
        f"/api/v1/hives/{hive}/weather?start=2026-10-18T00:00:00Z&end=2026-10-19T00:00:00Z",
        headers=auth(owner),
    )
    points = r.json()
    assert [p["temp_c"] for p in points] == [24.5, 26.0] and points[1]["precip_mm"] == 1.2


async def test_a_failed_fetch_does_not_stop_the_other_apiaries(
    engine: AsyncEngine,
) -> None:
    await setup_hive(engine)
    await setup_hive(engine)
    async with engine.begin() as c:
        await c.execute(
            text("UPDATE apiaries SET lat = 1, lon = 1 WHERE id = (SELECT id FROM apiaries LIMIT 1)")
        )
        await c.execute(text("UPDATE apiaries SET lat = 2, lon = 2 WHERE lat IS NULL"))

    async def flaky(lat: float, lon: float) -> dict[str, Any]:
        if lat == 1:
            raise OSError("no network")
        return OPEN_METEO

    assert await weather.refresh_all(engine, flaky) == 2
