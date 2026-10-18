"""Sensor readings: one row per value, deduplicated on (msg_id, idx, ts)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from smarthive.contracts.telemetry import Telemetry
from smarthive.ingest.base import Handler, Stored

# A reading older than this reached us late (a node that was offline sent its queue). The WebSocket feed
# does not push it as live; it tells the client to refetch the range instead.
LIVE_WINDOW = timedelta(minutes=5)

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
RETURNING ts, hive_id, quantity, value, quality
""")


def parse(node_id: str, doc: dict[str, Any]) -> Telemetry:
    return Telemetry.model_validate(doc).expect_node(node_id)


async def store(conn: AsyncConnection, t: Telemetry) -> Stored:
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
    rows = (await conn.execute(_INSERT, params)).all()
    inserted = len(rows)
    notify = None
    if inserted:
        cutoff = datetime.now(UTC) - LIVE_WINDOW
        latest: dict[tuple[Any, str], Any] = {}  # newest live reading per (hive, quantity)
        for r in sorted((r for r in rows if r.hive_id and r.ts >= cutoff), key=lambda r: r.ts):
            latest[(r.hive_id, r.quantity)] = r
        notify = {
            "kind": "telemetry",
            "node_id": t.node_id,
            "readings": inserted,
            "live": [
                {
                    "hive_id": str(r.hive_id),
                    "quantity": r.quantity,
                    "ts": r.ts.isoformat(),
                    "value": r.value,
                    "quality": r.quality,
                }
                for r in latest.values()
            ],
            "backfill": sorted({str(r.hive_id) for r in rows if r.hive_id and r.ts < cutoff}),
        }
    return Stored(str(t.msg_id), len(rs), inserted, notify)


HANDLER = Handler("telemetry", parse, store)
