import json
import uuid
from datetime import UTC, datetime

from pi_node import payload
from pi_node.dht11 import Measurement

TS = datetime(2026, 10, 6, 14, 4, 0, 120000, tzinfo=UTC)


def test_telemetry_matches_the_contract() -> None:
    samples = [payload.Sample(TS, 8712345, True, Measurement(35.0, 58.0)), payload.Sample(TS, 8772343, False, None)]
    doc = json.loads(payload.telemetry("node-0001", "boot", samples))

    assert doc["schema"] == "smarthive.telemetry/1.0"
    assert uuid.UUID(doc["msg_id"]).version == 7
    assert doc["sent_at"].endswith("Z")
    assert doc["readings"] == [
        {"ts": "2026-10-06T14:04:00.120Z", "mono_ms": 8712345, "clock_synced": True, "sensor": "dht11-0",
         "quantity": "temp_in", "value": 35.0, "unit": "degC", "quality": "ok"},
        {"ts": "2026-10-06T14:04:00.120Z", "mono_ms": 8712345, "clock_synced": True, "sensor": "dht11-0",
         "quantity": "rh_in", "value": 58.0, "unit": "pct_rh", "quality": "ok"},
        {"ts": "2026-10-06T14:04:00.120Z", "mono_ms": 8772343, "clock_synced": False, "sensor": "dht11-0",
         "quantity": "temp_in", "value": None, "unit": "degC", "quality": "read_error"},
        {"ts": "2026-10-06T14:04:00.120Z", "mono_ms": 8772343, "clock_synced": False, "sensor": "dht11-0",
         "quantity": "rh_in", "value": None, "unit": "pct_rh", "quality": "read_error"},
    ]


def test_uuid7_sorts_by_time() -> None:
    ids = [payload.uuid7() for _ in range(3)]
    assert [i[:13] for i in ids] == sorted(i[:13] for i in ids)


def test_status() -> None:
    assert json.loads(payload.status("online", "b")) == {"state": "online", "boot_id": "b"}
    assert json.loads(payload.status("offline", reason="shutdown")) == {"state": "offline", "reason": "shutdown"}
    assert payload.topic("node-0001", "status") == "smarthive/v1/nodes/node-0001/status"
