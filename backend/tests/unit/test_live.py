"""What the live feed turns a notification into, and who it goes to. No database."""

import json

from smarthive.alerts.store import ALERT_CHANNEL
from smarthive.api.live import Hub, Subscriber, messages
from smarthive.ingest.handler import CHANNEL

HIVE, OTHER = "8d0c0000-0000-0000-0000-000000000001", "8d0c0000-0000-0000-0000-000000000002"


def test_telemetry_becomes_live_readings_and_a_backfill_notice() -> None:
    reading = {"hive_id": HIVE, "quantity": "temp_in", "ts": "t", "value": 35, "quality": "ok"}
    note = {"kind": "telemetry", "live": [reading], "backfill": [OTHER]}
    assert messages(CHANNEL, note) == [
        (HIVE, {"type": "reading", **reading}),
        (OTHER, {"type": "backfill", "hive_id": OTHER}),
    ]


def test_a_message_reaches_only_the_sockets_subscribed_to_its_hive() -> None:
    hub = Hub()
    mine, theirs, admin = Subscriber(False, {HIVE}), Subscriber(False, {OTHER}), Subscriber(True)
    for s in (mine, theirs, admin):
        hub.add(s)
    note = {"kind": "node_status", "node_id": "n", "status": "offline", "hive_id": HIVE}
    hub.dispatch(CHANNEL, json.dumps(note))
    assert mine.queue.qsize() == 1 and theirs.queue.empty() and admin.queue.empty()


def test_an_alert_without_a_hive_goes_to_administrators_only() -> None:
    hub = Hub()
    user, admin = Subscriber(False, {HIVE}), Subscriber(True)
    hub.add(user)
    hub.add(admin)
    alert = {
        "alert_id": "a",
        "state": "open",
        "severity": "warning",
        "title": "Node offline",
        "hive_id": None,
    }
    hub.dispatch(ALERT_CHANNEL, json.dumps(alert))
    assert user.queue.empty() and admin.queue.get_nowait()["type"] == "alert"


def test_a_garbled_notification_is_dropped() -> None:
    hub = Hub()
    sub = Subscriber(True, {HIVE})
    hub.add(sub)
    hub.dispatch(CHANNEL, "not json")
    hub.dispatch(CHANNEL, json.dumps({"kind": "event"}))  # missing fields
    assert sub.queue.empty()


def test_a_full_queue_marks_the_socket_as_too_slow() -> None:
    hub = Hub()
    sub = Subscriber(False, {HIVE})
    hub.add(sub)
    note = json.dumps({"kind": "node_status", "node_id": "n", "status": "online", "hive_id": HIVE})
    for _ in range(sub.queue.maxsize + 1):
        hub.dispatch(CHANNEL, note)
    assert sub.overflowed
