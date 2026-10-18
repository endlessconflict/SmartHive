"""Vision summary of one ten-minute window: traffic counts and the Varroa window."""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from smarthive.contracts.summary import Summary
from smarthive.ingest.base import Handler, Stored

# Deduplicated on msg_id and on (node_id, window_start), so a re-sent window never counts twice.
_INSERT = text("""
INSERT INTO vision_summaries (node_id, hive_id, window_start, window_end, frames_analyzed, counts,
                              varroa_classified, varroa_positive, msg_id)
VALUES (:node_id,
        (SELECT a.hive_id FROM node_assignments a
          WHERE a.node_id = :node_id AND a.valid @> CAST(:window_start AS timestamptz) LIMIT 1),
        CAST(:window_start AS timestamptz), :window_end, :frames_analyzed, CAST(:counts AS jsonb),
        :varroa_classified, :varroa_positive, CAST(:msg_id AS uuid))
ON CONFLICT DO NOTHING
RETURNING 1
""")


def parse(node_id: str, doc: dict[str, Any]) -> Summary:
    return Summary.model_validate(doc).expect_node(node_id)


async def store(conn: AsyncConnection, s: Summary) -> Stored:
    params = {
        "node_id": s.node_id,
        "window_start": s.window.start,
        "window_end": s.window.end,
        "frames_analyzed": s.frames_analyzed,
        "counts": json.dumps(s.counts),
        "varroa_classified": s.varroa.bees_classified,
        "varroa_positive": s.varroa.positive,
        "msg_id": str(s.msg_id),
    }
    if (await conn.execute(_INSERT, params)).first() is None:
        return Stored(str(s.msg_id), 1, 0)
    return Stored(str(s.msg_id), 1, 1, {"kind": "summary", "node_id": s.node_id})


HANDLER = Handler("summary", parse, store)
