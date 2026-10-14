"""Validate one telemetry message and store it idempotently. No MQTT in here, so it is easy to test."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.contracts.telemetry import Telemetry

TOPIC_FILTER = "smarthive/v1/nodes/+/telemetry"
MAX_PAYLOAD_BYTES = 256 * 1024
_TOPIC = re.compile(r"^smarthive/v1/nodes/([^/]+)/telemetry$")

log = logging.getLogger("smarthive.ingest")


class Rejected(Exception):
    """The message is not a valid telemetry batch. Nothing is stored."""

    def __init__(self, reason: str, errors: list[dict[str, str]] | None = None, msg_id: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.errors = errors or []
        self.msg_id = msg_id


@dataclass(frozen=True)
class Result:
    node_id: str
    msg_id: str
    readings: int
    inserted: int

    @property
    def duplicates(self) -> int:
        return self.readings - self.inserted


def validate(topic: str, payload: bytes) -> Telemetry:
    """All or nothing: one failed rule rejects the whole batch, so a re-sent batch means the same."""
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise Rejected("payload_too_large")
    match = _TOPIC.match(topic)
    if match is None:
        raise Rejected("unexpected_topic")
    try:
        doc: Any = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError:
        raise Rejected("not_utf8") from None
    except (ValueError, RecursionError):
        raise Rejected("not_json") from None
    if not isinstance(doc, dict):
        raise Rejected("not_a_json_object")
    msg_id = doc.get("msg_id")
    try:
        telemetry = Telemetry.model_validate(doc)
    except ValidationError as e:
        errors = [{"loc": ".".join(map(str, err["loc"])), "msg": err["msg"]} for err in e.errors()[:5]]
        raise Rejected("schema_violation", errors, msg_id if isinstance(msg_id, str) else None) from None
    if telemetry.node_id != match[1]:
        raise Rejected("node_id_mismatch", msg_id=str(telemetry.msg_id))
    return telemetry


# One multi-row statement, so RETURNING gives a reliable inserted count. hive_id comes from the
# node's assignment at the time of the reading, not at the time of arrival; NULL when unassigned.
_INSERT = text("""
INSERT INTO readings (ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, msg_id, idx)
SELECT r.ts, :node_id,
       (SELECT a.hive_id FROM node_assignments a WHERE a.node_id = :node_id AND a.valid @> r.ts LIMIT 1),
       r.quantity, r.value, r.quality, r.sensor, r.clock_synced, CAST(:msg_id AS uuid), r.idx
FROM unnest(
    CAST(:ts AS timestamptz[]), CAST(:idx AS smallint[]), CAST(:quantity AS text[]),
    CAST(:value AS float8[]), CAST(:quality AS text[]), CAST(:sensor AS text[]),
    CAST(:clock_synced AS boolean[])
) AS r(ts, idx, quantity, value, quality, sensor, clock_synced)
ON CONFLICT DO NOTHING
RETURNING 1
""")


async def insert(engine: AsyncEngine, t: Telemetry) -> int:
    """Insert the batch in one transaction. Returns how many rows were new (0 for a re-sent batch)."""
    rs = t.readings
    params = {
        "node_id": t.node_id,
        "msg_id": str(t.msg_id),
        "ts": [r.ts for r in rs],
        "idx": list(range(len(rs))),
        "quantity": [r.quantity for r in rs],
        "value": [r.value for r in rs],
        "quality": [r.quality for r in rs],
        "sensor": [r.sensor for r in rs],
        "clock_synced": [r.clock_synced for r in rs],
    }
    async with engine.begin() as conn:
        return len((await conn.execute(_INSERT, params)).all())


def _fields(**fields: object) -> dict[str, dict[str, object]]:
    return {"fields": fields}


async def ingest(engine: AsyncEngine, topic: str, payload: bytes) -> Result | None:
    """Validate and store. A rejected message is logged and returns None; database errors propagate."""
    try:
        telemetry = validate(topic, payload)
    except Rejected as e:
        log.warning(
            "telemetry_rejected",
            extra=_fields(
                topic=topic,
                reason=e.reason,
                errors=e.errors,
                msg_id=e.msg_id,
                payload=payload[:200].decode("utf-8", "replace"),
            ),
        )
        return None
    inserted = await insert(engine, telemetry)
    result = Result(telemetry.node_id, str(telemetry.msg_id), len(telemetry.readings), inserted)
    log.info(
        "telemetry_ingested",
        extra=_fields(
            node_id=result.node_id,
            msg_id=result.msg_id,
            readings=result.readings,
            inserted=result.inserted,
            duplicates=result.duplicates,
        ),
    )
    return result
