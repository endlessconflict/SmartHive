import json
import os
import sys
from pathlib import Path

import pytest

from pi_node.device_token import RETRY_S, DeviceToken


class Message:
    def __init__(self, topic: str, body: bytes) -> None:
        self.topic = topic
        self.payload = body


class Client:
    """What DeviceToken uses of paho, recording what it would send."""

    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.published: list[tuple[str, bytes, int]] = []
        self.subscribed: list[str] = []
        self.callbacks: dict[str, object] = {}

    def is_connected(self) -> bool:
        return self.connected

    def publish(self, topic: str, body: bytes, qos: int = 0) -> None:
        self.published.append((topic, body, qos))

    def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscribed.append(topic)

    def message_callback_add(self, topic: str, callback: object) -> None:
        self.callbacks[topic] = callback

    def deliver(self, body: bytes) -> None:
        [(topic, callback)] = self.callbacks.items()
        callback(self, None, Message(topic, body))  # type: ignore[operator]


REQ = "smarthive/v1/nodes/node-0001/token/req"
ANSWER = "smarthive/v1/nodes/node-0001/token"


def token(tmp_path: Path, now: list[float] | None = None) -> DeviceToken:
    now = now if now is not None else [0.0]
    return DeviceToken("node-0001", tmp_path / "state" / "device_token", clock=lambda: now[0])


def test_without_a_token_the_node_asks_on_connect_and_saves_the_answer(tmp_path: Path) -> None:
    t, c = token(tmp_path), Client()
    t.subscribe(c)
    assert c.subscribed == [ANSWER] and c.published == [(REQ, b"{}", 1)]
    c.deliver(json.dumps({"token": "abc"}).encode())
    assert t.value == "abc"
    assert (tmp_path / "state" / "device_token").read_text() == "abc\n"
    if sys.platform != "win32":
        assert os.stat(tmp_path / "state" / "device_token").st_mode & 0o777 == 0o600


def test_a_saved_token_is_reused_after_a_restart(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "device_token").write_text("kept\n")
    t, c = token(tmp_path), Client()
    t.subscribe(c)
    assert t.value == "kept" and c.published == []


def test_an_unanswered_request_is_repeated_but_not_flooded(tmp_path: Path) -> None:
    now = [0.0]
    t, c = token(tmp_path, now), Client()
    t.subscribe(c)
    t.request(c)
    assert len(c.published) == 1
    now[0] = RETRY_S
    t.request(c)
    assert len(c.published) == 2
    offline = Client(connected=False)
    now[0] = 3 * RETRY_S
    t.request(offline)
    assert offline.published == []


def test_a_refused_token_is_forgotten_and_asked_for_again(tmp_path: Path) -> None:
    t, c = token(tmp_path), Client()
    t.subscribe(c)
    c.deliver(b'{"token": "old"}')
    t.refused(c)
    assert t.value is None and c.published[-1][0] == REQ
    c.deliver(b'{"token": "new"}')
    assert t.value == "new"


@pytest.mark.parametrize("body", [b"not json", b"{}", b'{"token": ""}', b'{"token": 5}'])
def test_a_bad_answer_is_ignored(tmp_path: Path, body: bytes) -> None:
    t, c = token(tmp_path), Client()
    t.subscribe(c)
    c.deliver(body)
    assert t.value is None and not (tmp_path / "state" / "device_token").exists()
