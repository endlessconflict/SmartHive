"""Events, summaries, health and status against a real TimescaleDB, plus the node registry and NOTIFY."""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.ingest.handler import CHANNEL, ingest

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "fixtures"
NODE = "node-0001"


def load(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return doc


def topic(kind: str, node: str = NODE) -> str:
    return f"smarthive/v1/nodes/{node}/{kind}"


def raw(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc).encode()


async def scalar(engine: AsyncEngine, sql: str) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar_one_or_none()


async def assign_hive(engine: AsyncEngine, node: str = NODE) -> str:
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO users VALUES (gen_random_uuid(), 'a@b.c', 'A', 'x', 'admin')"))
        owner = (await conn.execute(text("SELECT id FROM users"))).scalar_one()
        apiary = (
            await conn.execute(
                text(
                    "INSERT INTO apiaries (id, owner_id, name) VALUES (gen_random_uuid(), :o, 'a') "
                    "RETURNING id"
                ),
                {"o": owner},
            )
        ).scalar_one()
        hive = (
            await conn.execute(
                text(
                    "INSERT INTO hives (id, apiary_id, name) VALUES (gen_random_uuid(), :a, 'h') RETURNING id"
                ),
                {"a": apiary},
            )
        ).scalar_one()
        await conn.execute(text("INSERT INTO nodes (id, is_simulated) VALUES (:n, false)"), {"n": node})
        await conn.execute(
            text("INSERT INTO node_assignments VALUES (:n, :h, tstzrange('2026-10-01', '2026-11-01'))"),
            {"n": node, "h": hive},
        )
    return str(hive)


# --- events -----------------------------------------------------------------------------------------------


async def test_an_event_is_stored_once_with_its_hive(engine: AsyncEngine) -> None:
    hive = await assign_hive(engine)
    first = await ingest(engine, topic("events"), raw(load("event_threat.json")))
    second = await ingest(engine, topic("events"), raw(load("event_threat.json")))
    assert first is not None and first.stored.inserted == 1
    assert second is not None and second.stored.inserted == 0
    assert await scalar(engine, "SELECT count(*) FROM detection_events") == 1
    assert str(await scalar(engine, "SELECT hive_id FROM detection_events")) == hive
    assert await scalar(engine, "SELECT cls FROM detection_events") == "hornet"
    assert await scalar(engine, "SELECT models->>'stage1' FROM detection_events") == "yolo11n-320-int8@1.0.0"


async def test_a_repeated_sighting_is_a_new_row_in_the_same_episode(engine: AsyncEngine) -> None:
    again = load("event_threat.json")
    again["msg_id"] = "0190f5a3-9999-7d4e-8f50-a1b2c3d4e5f6"
    again["event"]["last_seen"] = "2026-10-06T14:09:00Z"
    await ingest(engine, topic("events"), raw(load("event_threat.json")))
    await ingest(engine, topic("events"), raw(again))
    assert await scalar(engine, "SELECT count(*) FROM detection_events") == 2
    assert await scalar(engine, "SELECT count(DISTINCT episode_id) FROM detection_events") == 1


async def test_an_event_without_an_episode_is_its_own_episode(engine: AsyncEngine) -> None:
    doc = load("event_threat.json")
    doc["event"] = {"type": "sensor_fault", "cls": None}
    await ingest(engine, topic("events"), raw(doc))
    assert await scalar(engine, "SELECT episode_id = msg_id FROM detection_events") is True
    assert await scalar(engine, "SELECT first_seen = last_seen FROM detection_events") is True


async def test_an_event_for_an_image_that_has_not_arrived_is_kept(engine: AsyncEngine) -> None:
    await ingest(engine, topic("events"), raw(load("event_threat.json")))
    assert await scalar(engine, "SELECT count(*) FROM images") == 0
    assert await scalar(engine, "SELECT image_id IS NOT NULL FROM detection_events") is True


# --- summaries --------------------------------------------------------------------------------------------


async def test_a_summary_window_counts_once(engine: AsyncEngine) -> None:
    doc = load("summary_valid.json")
    resent = copy.deepcopy(doc)
    resent["msg_id"] = "0190f5a4-aaaa-7e5f-9061-b2c3d4e5f607"  # same window, new message id
    first = await ingest(engine, topic("summary"), raw(doc))
    assert first is not None and first.stored.inserted == 1
    assert (await ingest(engine, topic("summary"), raw(doc))).stored.inserted == 0  # type: ignore[union-attr]
    assert (await ingest(engine, topic("summary"), raw(resent))).stored.inserted == 0  # type: ignore[union-attr]
    assert await scalar(engine, "SELECT count(*) FROM vision_summaries") == 1
    assert await scalar(engine, "SELECT varroa_positive FROM vision_summaries") == 41
    assert await scalar(engine, "SELECT counts->>'hornet' FROM vision_summaries") == "4"


# --- health -----------------------------------------------------------------------------------------------


async def test_health_is_stored_as_received_and_marks_the_node_online(engine: AsyncEngine) -> None:
    await ingest(engine, topic("health"), raw(load("health_valid.json")))
    assert await scalar(engine, "SELECT data->>'config_version' FROM node_health") == "7"
    assert await scalar(engine, f"SELECT status FROM nodes WHERE id = '{NODE}'") == "online"


async def test_health_from_an_unsynced_clock_is_stamped_with_the_arrival_time(engine: AsyncEngine) -> None:
    doc = load("health_valid.json")
    doc["clock_synced"] = False
    doc["sent_at"] = "1970-01-01T00:01:00Z"
    await ingest(engine, topic("health"), raw(doc))
    assert await scalar(engine, "SELECT ts > now() - interval '1 minute' FROM node_health") is True


# --- status and the registry ------------------------------------------------------------------------------


async def test_the_first_message_registers_the_node(engine: AsyncEngine) -> None:
    await ingest(engine, topic("telemetry"), (FIXTURES / "telemetry_valid.json").read_bytes())
    assert await scalar(engine, f"SELECT is_simulated FROM nodes WHERE id = '{NODE}'") is False
    assert await scalar(engine, f"SELECT last_seen_at IS NOT NULL FROM nodes WHERE id = '{NODE}'") is True
    assert await scalar(engine, f"SELECT device_token_hash IS NULL FROM nodes WHERE id = '{NODE}'") is True


async def test_the_node_id_decides_whether_it_is_simulated(engine: AsyncEngine) -> None:
    doc = load("health_valid.json")
    doc["node_id"] = "sim-0042"
    await ingest(engine, topic("health", "sim-0042"), raw(doc))
    assert await scalar(engine, "SELECT is_simulated FROM nodes WHERE id = 'sim-0042'") is True


async def test_telemetry_alone_does_not_prove_the_node_is_online(engine: AsyncEngine) -> None:
    await ingest(engine, topic("telemetry"), (FIXTURES / "telemetry_valid.json").read_bytes())
    assert await scalar(engine, f"SELECT status FROM nodes WHERE id = '{NODE}'") == "unknown"


async def test_the_last_will_and_the_online_message_move_the_status(engine: AsyncEngine) -> None:
    online = await ingest(engine, topic("status"), raw({"state": "online", "boot_id": "b1"}))
    assert online is not None and online.stored.inserted == 1
    assert await scalar(engine, f"SELECT status FROM nodes WHERE id = '{NODE}'") == "online"
    await ingest(engine, topic("status"), raw({"state": "offline"}))
    assert await scalar(engine, f"SELECT status FROM nodes WHERE id = '{NODE}'") == "offline"


async def test_a_redelivered_retained_status_changes_nothing(engine: AsyncEngine) -> None:
    await ingest(engine, topic("status"), raw({"state": "offline"}))
    again = await ingest(engine, topic("status"), raw({"state": "offline"}))
    assert again is not None and again.stored.inserted == 0


async def test_going_offline_keeps_the_last_time_the_node_was_heard(engine: AsyncEngine) -> None:
    await ingest(engine, topic("health"), raw(load("health_valid.json")))
    heard = await scalar(engine, f"SELECT last_seen_at FROM nodes WHERE id = '{NODE}'")
    await ingest(engine, topic("status"), raw({"state": "offline"}))
    assert await scalar(engine, f"SELECT last_seen_at FROM nodes WHERE id = '{NODE}'") == heard


async def test_a_rejected_message_registers_nothing(engine: AsyncEngine) -> None:
    doc = load("health_valid.json")
    doc["node_id"] = "node-0002"  # not the node in the topic
    assert await ingest(engine, topic("health"), raw(doc)) is None
    assert await scalar(engine, "SELECT count(*) FROM nodes") == 0


# --- NOTIFY -----------------------------------------------------------------------------------------------


async def test_a_notification_is_sent_when_the_transaction_commits(engine: AsyncEngine, db_url: str) -> None:
    listener = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    seen: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    await listener.add_listener(CHANNEL, lambda _c, _pid, _ch, payload: seen.put_nowait(json.loads(payload)))
    try:
        await ingest(engine, topic("events"), raw(load("event_threat.json")))
        await ingest(engine, topic("events"), raw(load("event_threat.json")))  # duplicate: no second notice
        message = await asyncio.wait_for(seen.get(), timeout=5)
        await asyncio.sleep(0.3)
    finally:
        await listener.close()
    assert message["kind"] == "event" and message["cls"] == "hornet" and message["node_id"] == NODE
    assert seen.empty()
