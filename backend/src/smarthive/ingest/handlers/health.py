"""Health snapshot, stored as received."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from smarthive.contracts.health import Health
from smarthive.ingest.base import Handler, Stored

_INSERT = text("""
INSERT INTO node_health (ts, node_id, data) VALUES (:ts, :node_id, CAST(:data AS jsonb))
ON CONFLICT DO NOTHING RETURNING 1
""")


class ParsedHealth:
    """The validated envelope plus the original document, which is what gets stored."""

    def __init__(self, health: Health, doc: dict[str, Any]) -> None:
        self.health = health
        self.doc = doc


def parse(node_id: str, doc: dict[str, Any]) -> ParsedHealth:
    return ParsedHealth(Health.model_validate(doc).expect_node(node_id), doc)


async def store(conn: AsyncConnection, p: ParsedHealth) -> Stored:
    h = p.health
    # a node with an unsynced clock reports a time we cannot trust; the arrival time is the honest one
    ts = h.sent_at if h.clock_synced else datetime.now(UTC)
    params = {"ts": ts, "node_id": h.node_id, "data": json.dumps(p.doc)}
    inserted = 1 if (await conn.execute(_INSERT, params)).first() else 0
    return Stored(str(h.msg_id), 1, inserted, {"kind": "health", "node_id": h.node_id} if inserted else None)


# Health goes out with QoS 0, so it is never queued: receiving one means the node is alive right now.
HANDLER = Handler("health", parse, store, liveness="online")
