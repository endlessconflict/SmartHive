import asyncio
import copy
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import aiomqtt
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from smarthive.config import Settings
from smarthive.ingest import service
from smarthive.ingest.handler import ingest

pytestmark = pytest.mark.integration

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "fixtures/telemetry_valid.json").read_text()
)
TOPIC = "smarthive/v1/nodes/node-0001/telemetry"
MOSQUITTO_IMAGE = "eclipse-mosquitto:2.0.22"


def payload(doc: dict[str, Any] | None = None) -> bytes:
    return json.dumps(doc or FIXTURE).encode()


async def count(engine: AsyncEngine, where: str = "true") -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(f"SELECT count(*) FROM readings WHERE {where}"))).scalar_one())


async def test_same_batch_twice_is_stored_once(engine: AsyncEngine) -> None:  # AC1
    first = await ingest(engine, TOPIC, payload())
    second = await ingest(engine, TOPIC, payload())
    assert first is not None and first.inserted == 3
    assert second is not None and second.inserted == 0 and second.duplicates == 3
    assert await count(engine) == 3


async def test_invalid_payload_is_logged_and_the_next_batch_is_stored(  # AC2
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="smarthive.ingest")
    assert await ingest(engine, TOPIC, b"{broken") is None
    bad = copy.deepcopy(FIXTURE)
    bad["readings"][0]["quality"] = "great"
    assert await ingest(engine, TOPIC, payload(bad)) is None
    assert await count(engine) == 0  # all or nothing

    assert (await ingest(engine, TOPIC, payload())) is not None
    assert await count(engine) == 3
    rejected = [r for r in caplog.records if r.getMessage() == "telemetry_rejected"]
    assert [r.fields["reason"] for r in rejected] == ["not_json", "schema_violation"]  # type: ignore[attr-defined]


async def test_read_error_stored_as_null_and_unknown_quantity_kept(engine: AsyncEngine) -> None:
    doc = copy.deepcopy(FIXTURE)
    doc["readings"].append(
        {
            "ts": "2026-10-06T14:06:00Z", "mono_ms": 1, "clock_synced": False, "sensor": "mhz19",
            "quantity": "co2_ppm", "value": 612, "unit": "ppm", "quality": "ok",
        }
    )  # fmt: skip
    await ingest(engine, TOPIC, payload(doc))
    assert await count(engine, "quality = 'read_error' AND value IS NULL") == 1
    assert await count(engine, "quantity = 'co2_ppm' AND value = 612 AND clock_synced = false") == 1


async def test_hive_id_is_resolved_by_reading_time(engine: AsyncEngine) -> None:
    user, apiary, hive = (str(uuid.uuid4()) for _ in range(3))
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO users VALUES (:u, 'a@b.c', 'A', 'x', 'admin', true, null, now())"), {"u": user}
        )
        await conn.execute(
            text("INSERT INTO apiaries (id, owner_id, name) VALUES (:a, :u, 'yard')"),
            {"a": apiary, "u": user},
        )
        await conn.execute(
            text("INSERT INTO hives (id, apiary_id, name) VALUES (:h, :a, 'h1')"), {"h": hive, "a": apiary}
        )
        await conn.execute(
            text("INSERT INTO nodes (id, is_simulated, device_token_hash) VALUES ('node-0001', false, 'x')")
        )
        # assigned from 14:00 (included) to 14:10 (excluded)
        await conn.execute(
            text(
                "INSERT INTO node_assignments VALUES ('node-0001', :h, "
                "tstzrange('2026-10-06T14:00:00Z', '2026-10-06T14:10:00Z'))"
            ),
            {"h": hive},
        )

    def reading(ts: str, quantity: str) -> dict[str, Any]:
        unit = "degC" if quantity == "temp_in" else "pct_rh"
        return {
            "ts": ts, "mono_ms": 1, "clock_synced": True, "sensor": "dht11-0",
            "quantity": quantity, "value": 1, "unit": unit, "quality": "ok",
        }  # fmt: skip

    doc = copy.deepcopy(FIXTURE)
    doc["readings"] = [
        reading("2026-10-06T13:59:59Z", "temp_in"),  # before the assignment
        reading("2026-10-06T14:00:00Z", "temp_in"),  # first instant
        reading("2026-10-06T14:09:59Z", "temp_in"),  # last instant
        reading("2026-10-06T14:10:00Z", "temp_in"),  # after
    ]
    await ingest(engine, TOPIC, payload(doc))
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT idx, hive_id FROM readings ORDER BY idx"))).all()
    assert [(i, h is not None) for i, h in rows] == [(0, False), (1, True), (2, True), (3, False)]
    assert str(rows[1][1]) == hive


async def test_end_to_end_through_mosquitto(engine: AsyncEngine, db_url: str, tmp_path: Path) -> None:
    conf = tmp_path / "mosquitto.conf"
    conf.write_text("listener 1883\nallow_anonymous true\n")  # test only: no TLS, no auth
    broker = (
        DockerContainer(MOSQUITTO_IMAGE)
        .with_exposed_ports(1883)
        .with_volume_mapping(str(conf), "/mosquitto/config/mosquitto.conf")
    )
    with broker:
        wait_for_logs(broker, "mosquitto version .* running")
        settings = Settings(
            db_url=db_url,
            mqtt_host=broker.get_container_host_ip(),
            mqtt_port=int(broker.get_exposed_port(1883)),
            mqtt_client_id=f"test-{uuid.uuid4().hex[:8]}",
        )
        stop = asyncio.Event()
        runner = asyncio.create_task(service.run(settings, stop))
        try:
            async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as pub:
                # the subscription may not exist yet; a re-sent batch is harmless, which is the point
                for _ in range(50):
                    await pub.publish(TOPIC, payload(), qos=1)
                    await asyncio.sleep(0.2)
                    if await count(engine) == 3:
                        break
                assert await count(engine) == 3
                await pub.publish(TOPIC, payload(), qos=1)  # duplicate
                await pub.publish(TOPIC, b"\xff garbage", qos=1)  # invalid
                await pub.publish(TOPIC, payload(), qos=1)  # duplicate again
                await asyncio.sleep(1.0)
            assert await count(engine) == 3
            assert not runner.done()  # the garbage did not stop the service
        finally:
            stop.set()
            await asyncio.wait_for(runner, timeout=10)
