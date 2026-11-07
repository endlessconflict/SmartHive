import json
import sqlite3
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pi_node import main, payload
from pi_node.dht11 import Measurement
from pi_node.main import Config
from pi_node.outbox import Outbox

TS = datetime(2026, 10, 6, 14, 4, 0, 120000, tzinfo=UTC)
TOPIC = "smarthive/v1/nodes/node-0001/telemetry"


def body(msg_id: str = "m1") -> bytes:
    return json.dumps({"msg_id": msg_id, "node_id": "node-0001", "readings": []}).encode()


@pytest.fixture
def outbox(tmp_path: Path):
    box = Outbox(tmp_path / "sub" / "outbox.db")
    yield box
    box.close()


def test_a_message_is_stored_whole_with_its_metadata(outbox: Outbox) -> None:
    outbox.add(TOPIC, body(), TS, True)
    [row] = outbox.pending()
    assert (row.msg_id, row.node_id, row.kind, row.topic) == ("m1", "node-0001", "telemetry", TOPIC)
    assert row.payload == body()  # the exact bytes, so a re-send keeps its msg_id
    assert row.created_at == 1791295440120
    assert row.clock_synced is True


def test_pending_keeps_write_order_when_the_clock_jumps_back(outbox: Outbox) -> None:
    outbox.add(TOPIC, body("first"), TS, True)
    outbox.add(TOPIC, body("second"), TS - timedelta(days=30), False)  # booted without RTC or NTP
    assert [r.msg_id for r in outbox.pending()] == ["first", "second"]


def test_events_leave_before_telemetry(outbox: Outbox) -> None:
    outbox.add(TOPIC, body("reading"), TS, True)
    outbox.add("smarthive/v1/nodes/node-0001/events", body("hornet"), TS, True)
    assert [r.msg_id for r in outbox.pending()] == ["hornet", "reading"]


def test_pending_respects_the_limit(outbox: Outbox) -> None:
    for i in range(3):
        outbox.add(TOPIC, body(f"m{i}"), TS, True)
    assert [r.msg_id for r in outbox.pending(limit=2)] == ["m0", "m1"]


def test_the_database_uses_wal(tmp_path: Path) -> None:
    Outbox(tmp_path / "o.db").close()
    db = sqlite3.connect(tmp_path / "o.db")
    assert db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    db.close()


def test_a_write_survives_the_process_being_killed(tmp_path: Path) -> None:
    path = tmp_path / "o.db"
    script = f"""
import json, os
from datetime import datetime, UTC
from pathlib import Path
from pi_node.outbox import Outbox
box = Outbox(Path({str(path)!r}))
box.add("t/telemetry", json.dumps({{"msg_id": "m1", "node_id": "n"}}).encode(), datetime.now(UTC), True)
os._exit(1)  # no close, no cleanup
"""
    done = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[1], check=False)
    assert done.returncode == 1

    box = Outbox(path)
    assert [r.msg_id for r in box.pending()] == ["m1"]
    box.close()


class FakeSensor:
    """Ends the node's loop at the second sample, so the first one has time to go out."""

    def __init__(self, stop: threading.Event) -> None:
        self.stop = stop
        self.reads = 0

    def read(self) -> Measurement:
        self.reads += 1
        if self.reads == 2:
            self.stop.set()
        return Measurement(35.0, 58.0)


class FakeInfo:
    rc = 0

    def wait_for_publish(self, timeout: float) -> None:
        pass

    def is_published(self) -> bool:
        return True


class FakeClient:
    def __init__(self, connected: bool) -> None:
        self.connected = connected
        self.published: list[bytes] = []

    def publish(self, topic: str, body: bytes, qos: int = 0, retain: bool = False) -> FakeInfo:
        if topic.endswith("/telemetry"):
            self.published.append(body)
        return FakeInfo()

    def is_connected(self) -> bool:
        return self.connected

    def disconnect(self) -> None:
        pass

    def loop_stop(self) -> None:
        pass


def run_once(monkeypatch: pytest.MonkeyPatch, box: object, connected: bool) -> FakeClient:
    client = FakeClient(connected)
    monkeypatch.setattr(main, "make_client", lambda *_: client)
    monkeypatch.setattr(main, "clock_synced", lambda: False)
    stop = threading.Event()
    cfg = Config("node-0001", 0.05, "h", 1, False, None, None, None)
    main.run(cfg, FakeSensor(stop), None, box, stop)  # type: ignore[arg-type]
    return client


def test_the_node_stores_each_sample_without_a_broker(monkeypatch: pytest.MonkeyPatch, outbox: Outbox) -> None:
    client = run_once(monkeypatch, outbox, connected=False)
    assert client.published == []
    row, _ = outbox.pending()
    doc = json.loads(row.payload)
    assert row.topic == payload.topic("node-0001", "telemetry")
    assert doc["node_id"] == "node-0001" and doc["msg_id"] == row.msg_id
    assert [r["quantity"] for r in doc["readings"]] == ["temp_in", "rh_in"]
    assert row.clock_synced is False


def test_with_a_broker_the_stored_bytes_are_what_goes_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    box = Outbox(tmp_path / "o.db")
    client = run_once(monkeypatch, box, connected=True)
    [unsent] = box.pending()  # the second sample, taken as the node stopped
    assert len(client.published) == 1
    sent_id = json.loads(client.published[0])["msg_id"]
    assert sent_id != unsent.msg_id
    assert box._db.execute("SELECT payload FROM outbox WHERE msg_id = ?", (sent_id,)).fetchone() == (client.published[0],)
    box.close()


def test_a_failing_disk_does_not_stop_the_node(monkeypatch: pytest.MonkeyPatch) -> None:
    class FullDisk:
        def add(self, *_: object) -> None:
            raise sqlite3.OperationalError("database or disk is full")

        def pending(self, limit: int = 100) -> None:
            raise sqlite3.OperationalError("disk I/O error")

    assert len(run_once(monkeypatch, FullDisk(), connected=True).published) == 2  # the readings still go out live
