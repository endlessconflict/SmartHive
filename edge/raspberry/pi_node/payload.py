"""Telemetry and status payloads of the messaging contract (docs/05-backend/04-messaging-contract.md)."""

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pi_node.dht11 import Measurement

SENSOR_ID = "dht11-0"


def topic(node_id: str, suffix: str) -> str:
    return f"smarthive/v1/nodes/{node_id}/{suffix}"


def uuid7() -> str:
    """48-bit Unix milliseconds, then random bits. Sorts by time; the server deduplicates on it."""
    b = bytearray((time.time_ns() // 1_000_000).to_bytes(6, "big") + os.urandom(10))
    b[6] = (b[6] & 0x0F) | 0x70
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Sample:
    ts: datetime
    mono_ms: int
    clock_synced: bool
    measurement: Measurement | None  # None: the sensor did not answer


def readings(s: Sample) -> list[dict]:
    m = s.measurement
    common = {"ts": iso(s.ts), "mono_ms": s.mono_ms, "clock_synced": s.clock_synced, "sensor": SENSOR_ID}
    return [
        {**common, "quantity": q, "value": None if m is None else getattr(m, field), "unit": u,
         "quality": "read_error" if m is None else "ok"}
        for q, u, field in (("temp_in", "degC", "temp_c"), ("rh_in", "pct_rh", "rh_pct"))
    ]


def telemetry(node_id: str, boot_id: str, samples: list[Sample]) -> bytes:
    doc = {
        "schema": "smarthive.telemetry/1.0",
        "msg_id": uuid7(),
        "node_id": node_id,
        "boot_id": boot_id,
        "sent_at": iso(datetime.now(UTC)),
        "readings": [r for s in samples for r in readings(s)],
    }
    return json.dumps(doc, separators=(",", ":")).encode()


def status(state: str, boot_id: str | None = None, reason: str | None = None) -> bytes:
    doc = {"state": state, "boot_id": boot_id, "reason": reason}
    return json.dumps({k: v for k, v in doc.items() if v is not None}).encode()
