import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pi_node.outbox import Outbox
from pi_node.uplink import MAX_BACKOFF_S, Uplink

TS = datetime(2026, 10, 6, 14, 4, 0, tzinfo=UTC)
TOPIC = "smarthive/v1/nodes/node-0001/telemetry"
FAR = float("inf")


def body(msg_id: str) -> bytes:
    return json.dumps({"msg_id": msg_id, "node_id": "node-0001"}).encode()


class Info:
    def __init__(self, acked: bool, error: Exception | None = None) -> None:
        self.acked, self.error = acked, error

    def wait_for_publish(self, _timeout: float) -> None:
        if self.error:
            raise self.error

    def is_published(self) -> bool:
        return self.acked


class Client:
    def __init__(self) -> None:
        self.connected = True
        self.acks = True
        self.error: Exception | None = None
        self.published: list[str] = []
        self.qos: list[int] = []

    def is_connected(self) -> bool:
        return self.connected

    def publish(self, _topic: str, payload: bytes, qos: int = 0) -> Info:
        self.published.append(json.loads(payload)["msg_id"])
        self.qos.append(qos)
        return Info(self.acks, self.error)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def outbox(tmp_path: Path):
    box = Outbox(tmp_path / "outbox.db")
    yield box
    box.close()


def fill(box: Outbox, *ids: str) -> None:
    for msg_id in ids:
        box.add(TOPIC, body(msg_id), TS, True)


def pending(box: Outbox) -> list[str]:
    return [r.msg_id for r in box.pending()]


def test_sends_oldest_first_at_qos_1_and_marks_them_sent(outbox: Outbox) -> None:
    fill(outbox, "a", "b", "c")
    client = Client()
    assert Uplink(client, outbox).drain(threading.Event(), FAR) == 3
    assert client.published == ["a", "b", "c"]
    assert client.qos == [1, 1, 1]
    assert pending(outbox) == []


def test_sent_rows_never_go_out_again_even_after_a_restart(tmp_path: Path) -> None:
    box = Outbox(tmp_path / "o.db")
    fill(box, "a")
    Uplink(Client(), box).drain(threading.Event(), FAR)
    box.close()

    box = Outbox(tmp_path / "o.db")
    client = Client()
    assert Uplink(client, box).drain(threading.Event(), FAR) == 0
    assert client.published == []
    box.close()


def test_without_a_connection_nothing_is_published_and_the_rows_wait(outbox: Outbox) -> None:
    fill(outbox, "a")
    client = Client()
    client.connected = False
    assert Uplink(client, outbox).drain(threading.Event(), FAR) == 0
    assert client.published == []
    assert pending(outbox) == ["a"]


def test_the_rows_go_out_when_the_connection_is_back(outbox: Outbox) -> None:
    fill(outbox, "a", "b")
    client = Client()
    client.connected = False
    uplink = Uplink(client, outbox)
    uplink.drain(threading.Event(), FAR)
    client.connected = True
    assert uplink.drain(threading.Event(), FAR) == 2
    assert client.published == ["a", "b"]


def test_a_timeout_without_puback_keeps_the_row_and_stops_the_order_from_breaking(outbox: Outbox) -> None:
    fill(outbox, "a", "b")
    client = Client()
    client.acks = False
    assert Uplink(client, outbox).drain(threading.Event(), FAR) == 0
    assert client.published == ["a"]  # "b" does not overtake it
    assert pending(outbox) == ["a", "b"]


@pytest.mark.parametrize("error", [RuntimeError("no connection"), ValueError("queue full")])
def test_a_refused_publish_keeps_the_row(outbox: Outbox, error: Exception) -> None:
    fill(outbox, "a")
    client = Client()
    client.error = error
    assert Uplink(client, outbox).drain(threading.Event(), FAR) == 0
    assert pending(outbox) == ["a"]


def test_a_failed_send_waits_with_a_growing_delay_then_retries_the_same_message(outbox: Outbox) -> None:
    fill(outbox, "a")
    client, clock = Client(), Clock()
    client.acks = False
    uplink = Uplink(client, outbox, clock)
    stop = threading.Event()

    uplink.drain(stop, FAR)
    uplink.drain(stop, FAR)  # still inside the delay
    assert client.published == ["a"]

    clock.now += 1.0  # at most 1 s the first time
    uplink.drain(stop, FAR)
    assert client.published == ["a", "a"]

    for _ in range(12):
        clock.now += MAX_BACKOFF_S
        uplink.drain(stop, FAR)
    assert uplink._delay == MAX_BACKOFF_S  # capped

    client.acks = True
    clock.now += MAX_BACKOFF_S
    assert uplink.drain(stop, FAR) == 1
    assert uplink._delay == 1.0  # a success starts over
    assert pending(outbox) == []


def test_a_new_message_waits_behind_the_backlog(outbox: Outbox) -> None:
    fill(outbox, "old")
    client = Client()
    uplink = Uplink(client, outbox)
    fill(outbox, "new")
    uplink.drain(threading.Event(), FAR)
    assert client.published == ["old", "new"]


def test_the_deadline_leaves_the_rest_for_later(outbox: Outbox) -> None:
    fill(outbox, "a", "b", "c")
    client, clock = Client(), Clock()

    def slow_publish(_topic: str, _payload: bytes, qos: int = 0) -> Info:
        clock.now += 1
        return Info(True)

    client.publish = slow_publish  # type: ignore[method-assign]
    assert Uplink(client, outbox, clock).drain(threading.Event(), clock.now + 2) == 2
    assert pending(outbox) == ["c"]


def test_stop_ends_the_drain(outbox: Outbox) -> None:
    fill(outbox, "a")
    stop = threading.Event()
    stop.set()
    assert Uplink(Client(), outbox).drain(stop, FAR) == 0


def test_purge_removes_old_sent_rows_and_never_pending_ones(outbox: Outbox) -> None:
    fill(outbox, "sent", "waiting")
    outbox.mark_sent("sent", at=TS)
    assert outbox.purge(older_than=TS + timedelta(days=1)) == 1
    assert pending(outbox) == ["waiting"]
    assert outbox.purge(older_than=TS + timedelta(days=1)) == 0
