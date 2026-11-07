"""US03: the real node code against a real broker that goes away, down to TimescaleDB. Nothing lost, nothing twice."""

import asyncio
import json
import socket
import sqlite3
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiomqtt
import pytest
from pi_node import main, payload
from pi_node.dht11 import Measurement
from pi_node.outbox import Outbox
from pi_node.uplink import Uplink
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from smarthive.config import Settings
from smarthive.ingest import service

pytestmark = pytest.mark.integration

REPO = Path(__file__).parents[3]
FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures/telemetry_valid.json").read_text())
MOSQUITTO_IMAGE = "eclipse-mosquitto:2.0.22"
NODE = "node-0001"
# The broker settings from infra/mosquitto/mosquitto.conf that this depends on, without the TLS
CONF = r"listener 1883\nallow_anonymous true\npersistence true\npersistence_location /mosquitto/data/\n"


async def until(check: Callable[[], Awaitable[bool]], what: str, timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while not await check():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        await asyncio.sleep(0.2)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return int(s.getsockname()[1])


class Stack:
    def __init__(self, broker: DockerContainer, host: str, port: int, settings: Settings) -> None:
        self.broker = broker
        self.host = host
        self.port = port
        self.settings = settings
        self._stop_ingest = asyncio.Event()
        self._ingest: asyncio.Task[None] | None = None

    def start_ingest(self) -> None:
        self._stop_ingest = asyncio.Event()
        self._ingest = asyncio.create_task(service.run(self.settings, self._stop_ingest))

    async def stop_ingest(self) -> None:
        if self._ingest is not None:
            self._stop_ingest.set()
            await asyncio.wait_for(self._ingest, timeout=10)
            self._ingest = None

    async def stop_broker(self) -> None:
        await asyncio.to_thread(self.broker.get_wrapped_container().stop)

    async def start_broker(self) -> None:
        await asyncio.to_thread(self.broker.get_wrapped_container().start)


@pytest.fixture
async def stack(engine: AsyncEngine, db_url: str) -> AsyncIterator[Stack]:
    """Mosquitto and the ingestor, with the ingestor's subscription proven by a message getting through."""
    port = free_port()
    # the config goes in through the command: a bind mount would be lost on the restart in some Docker setups
    broker = (
        DockerContainer(MOSQUITTO_IMAGE)
        .with_bind_ports(1883, port)
        .with_command(["sh", "-c", f"printf '{CONF}' > /tmp/m.conf && exec mosquitto -c /tmp/m.conf"])
    )
    with broker:
        wait_for_logs(broker, "mosquitto version .* running")
        host = broker.get_container_host_ip()
        settings = Settings(db_url=db_url, mqtt_host=host, mqtt_port=port, mqtt_client_id="test-ingest")
        running = Stack(broker, host, port, settings)
        running.start_ingest()
        probe = json.dumps({**FIXTURE, "node_id": "probe"}).encode()

        async def probe_stored() -> bool:
            async with aiomqtt.Client(host, port) as client:
                await client.publish("smarthive/v1/nodes/probe/telemetry", probe, qos=1)
            async with engine.connect() as conn:
                n = await conn.execute(text("SELECT count(*) FROM readings WHERE node_id = 'probe'"))
                return int(n.scalar_one()) > 0

        try:
            await until(probe_stored, "the ingestor to subscribe")
            yield running
        finally:
            await running.stop_ingest()


class Sensor:
    def read(self) -> Measurement:
        return Measurement(35.0, 58.0)


class Node:
    """main.run as on the Pi, in its own thread because it blocks. Stopping and starting it is a process restart."""

    def __init__(self, stack: Stack, path: Path) -> None:
        self.path = path
        self.cfg = main.Config(NODE, 0.2, stack.host, stack.port, False, None, None, None, outbox_path=path)
        self.stopping = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        def run() -> None:
            box = Outbox(self.path)  # SQLite connections stay on the thread that opened them
            main.run(self.cfg, Sensor(), None, box, self.stopping)
            box.close()

        self.stopping = threading.Event()
        self.thread = threading.Thread(target=run)
        self.thread.start()

    async def stop(self) -> None:
        assert self.thread is not None
        self.stopping.set()
        await asyncio.to_thread(self.thread.join)

    def rows(self) -> list[tuple[str, int | None]]:
        """(msg_id, sent_at) in write order."""
        db = sqlite3.connect(self.path)
        try:
            return db.execute("SELECT msg_id, sent_at FROM outbox ORDER BY rowid").fetchall()
        finally:
            db.close()

    def unsent(self) -> list[str]:
        return [msg_id for msg_id, sent_at in self.rows() if sent_at is None]


async def stored(engine: AsyncEngine) -> dict[str, int]:
    """msg_id -> rows in TimescaleDB, in arrival order."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT CAST(msg_id AS text) AS m, count(*) AS n FROM readings WHERE node_id = :n "
                "GROUP BY msg_id ORDER BY min(received_at)"
            ),
            {"n": NODE},
        )
        return {r.m: r.n for r in rows}


@pytest.fixture(autouse=True)
def synced_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "clock_synced", lambda: True)


async def test_a_broker_outage_loses_nothing_and_stores_nothing_twice(
    stack: Stack, engine: AsyncEngine, tmp_path: Path
) -> None:
    node = Node(stack, tmp_path / "outbox.db")
    node.start()
    try:

        async def some_stored() -> bool:
            return len(await stored(engine)) >= 2

        await until(some_stored, "readings with the broker up")

        await stack.stop_broker()

        async def backlog() -> bool:
            return len(node.unsent()) >= 8

        await until(backlog, "samples to pile up on disk")

        await node.stop()  # the node restarts while offline: the backlog has to be on disk, not in memory
        offline = node.unsent()
        node.start()

        await stack.start_broker()

        async def caught_up() -> bool:
            return not set(offline) & set(node.unsent())

        await until(caught_up, "the backlog to be sent")
    finally:
        await node.stop()

    sent = [msg_id for msg_id, sent_at in node.rows() if sent_at is not None]

    async def all_arrived() -> bool:
        return set(sent) <= set(await stored(engine))

    await until(all_arrived, "every message marked sent to reach the database")

    in_db = await stored(engine)
    assert set(in_db) <= {msg_id for msg_id, _ in node.rows()}
    assert set(in_db.values()) == {2}  # temperature and humidity, each once
    assert [m for m in in_db if m in offline] == offline  # oldest first


async def test_messages_wait_for_the_ingestor_across_a_broker_restart(
    stack: Stack, engine: AsyncEngine, tmp_path: Path
) -> None:
    """The broker's PUBACK ends the node's responsibility, so the broker must still hold them for the ingestor."""
    node = Node(stack, tmp_path / "outbox.db")
    node.start()
    try:

        async def some_stored() -> bool:
            return len(await stored(engine)) >= 2

        await until(some_stored, "readings with the broker up")
        await stack.stop_ingest()
        await stack.stop_broker()
        await stack.start_broker()

        async def several_handed_over() -> bool:
            handed_over = {msg_id for msg_id, sent_at in node.rows() if sent_at is not None}
            return len(handed_over - set(await stored(engine))) >= 5

        await until(several_handed_over, "the node to hand messages to the broker")
    finally:
        await node.stop()

    stack.start_ingest()
    sent = [msg_id for msg_id, sent_at in node.rows() if sent_at is not None]

    async def all_arrived() -> bool:
        return set(sent) <= set(await stored(engine))

    await until(all_arrived, "the messages the broker confirmed to reach the database", timeout_s=20)


async def test_a_crash_between_puback_and_mark_is_dropped_by_the_server(
    stack: Stack, engine: AsyncEngine, tmp_path: Path
) -> None:
    cfg = main.Config(NODE, 60, stack.host, stack.port, False, None, None, None)
    client = main.make_client(cfg, "boot")
    box = Outbox(tmp_path / "outbox.db")
    try:
        sample = payload.Sample(datetime.now(UTC), 1, True, Measurement(35.0, 58.0))
        box.add(payload.topic(NODE, "telemetry"), payload.telemetry(NODE, "boot", [sample]), sample.ts, True)
        [row] = box.pending()

        async def connected() -> bool:
            return bool(client.is_connected())

        await until(connected, "the node to connect")

        crashed = threading.Event()
        unmarked: Any = box
        real_mark = box.mark_sent
        unmarked.mark_sent = lambda _msg_id: crashed.set()  # the process dies before the mark is written
        assert Uplink(client, box).drain(crashed, float("inf")) == 1
        assert [r.msg_id for r in box.pending()] == [row.msg_id]

        unmarked.mark_sent = real_mark  # after the restart it goes out a second time, and is marked
        assert Uplink(client, box).drain(threading.Event(), float("inf")) == 1
        assert box.pending() == []

        async def arrived() -> bool:
            return row.msg_id in await stored(engine)

        await until(arrived, "the message to reach the database")
        await asyncio.sleep(1.5)  # the second delivery has had time to be handled
        assert await stored(engine) == {row.msg_id: 2}
    finally:
        client.loop_stop()
        box.close()


def test_the_real_broker_config_keeps_sessions_across_restarts() -> None:
    conf = (REPO / "infra/mosquitto/mosquitto.conf").read_text()
    assert "persistence true" in conf and "persistence_location /mosquitto/data/" in conf
