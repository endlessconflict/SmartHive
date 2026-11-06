"""Weight from the node's message to the API. It has no code of its own: it must work as any other reading."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.app import create_app
from smarthive.config import Settings
from smarthive.ingest.handler import ingest
from tests.integration.test_alerts import auth, setup_hive
from tests.integration.test_api_auth import SECRET, add_user

pytestmark = pytest.mark.integration

# (minutes after the start of the hour, value, quality), as the node sends them every five minutes
WEIGHTS = [
    (0, 41.2, "ok"),
    (5, 41.3, "ok"),
    (10, None, "read_error"),
    (15, 99.99, "clipped"),
    (20, 41.4, "ok"),
]


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(jwt_secret=SECRET), engine)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


def message(node: str, hour: datetime) -> bytes:
    def reading(minutes: int, value: float | None, quality: str) -> dict[str, Any]:
        ts = (hour + timedelta(minutes=minutes)).isoformat()
        return {
            "ts": ts, "mono_ms": minutes, "clock_synced": True, "sensor": "hx711-0",
            "quantity": "weight", "value": value, "unit": "kg", "quality": quality,
        }  # fmt: skip

    return json.dumps(
        {
            "schema": "smarthive.telemetry/1.0",
            "msg_id": str(uuid4()),
            "node_id": node,
            "boot_id": "boot",
            "sent_at": hour.isoformat(),
            "readings": [reading(*w) for w in WEIGHTS],
        }
    ).encode()


async def test_weight_is_stored_and_served(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=3)
    body = message(node, hour)
    topic = f"smarthive/v1/nodes/{node}/telemetry"

    result = await ingest(engine, topic, body)
    assert result is not None and result.stored.inserted == len(WEIGHTS)
    again = await ingest(engine, topic, body)  # QoS 1 can deliver it twice
    assert again is not None and again.stored.inserted == 0

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT hive_id, sensor, value, quality FROM readings WHERE node_id = :n ORDER BY ts"),
                {"n": node},
            )
        ).all()
    assert [(r.value, r.quality) for r in rows] == [(v, q) for _, v, q in WEIGHTS]
    assert {(r.hive_id, r.sensor) for r in rows} == {(hive, "hx711-0")}

    url = f"/api/v1/hives/{hive}/readings"
    raw = (await client.get(url, params={"quantity": "weight"}, headers=auth(owner))).json()
    # read errors and clipped values stay out
    assert [p["value"] for p in raw["points"]] == [41.2, 41.3, 41.4]

    params = {"quantity": "weight", "bucket": "1h"}
    [hourly] = (await client.get(url, params=params, headers=auth(owner))).json()["points"]
    assert hourly["value"] == pytest.approx(41.3) and hourly["n"] == 3
    assert (hourly["min"], hourly["max"]) == (41.2, 41.4)

    latest = (await client.get(f"/api/v1/hives/{hive}/latest", headers=auth(owner))).json()["latest"]
    assert latest["weight"]["value"] == 41.4

    export = await client.get(f"/api/v1/exports/readings?hive_id={hive}&quantity=weight", headers=auth(owner))
    table = [x for x in export.text.splitlines() if not x.startswith("# ")]
    assert len(table) == 1 + len(WEIGHTS) and "clipped" in table[4]  # the export keeps every quality flag


async def test_weight_of_a_hive_is_private(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    _, hive, _ = await setup_hive(engine)
    other = await add_user(engine, f"x-{uuid4().hex[:6]}@example.com")
    url = f"/api/v1/hives/{hive}/readings"
    assert (await client.get(url, params={"quantity": "weight"}, headers=auth(other))).status_code == 404
    assert (await client.get(url, params={"quantity": "weight"})).status_code == 401
