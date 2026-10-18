"""Detection events and node-side alarms. A repeated sighting is a new message with the same episode_id."""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from smarthive.contracts.event import Event
from smarthive.ingest.base import Handler, Stored

# An event without an episode (sensor_fault, storage_low, ...) is its own episode. A node that is not yet
# assigned to a hive leaves hive_id NULL, as for readings.
_INSERT = text("""
INSERT INTO detection_events (msg_id, episode_id, node_id, hive_id, type, cls, first_seen, last_seen,
                              max_conf, frames_positive, frames_window, image_id, models)
VALUES (CAST(:msg_id AS uuid), CAST(:episode_id AS uuid), :node_id,
        (SELECT a.hive_id FROM node_assignments a
          WHERE a.node_id = :node_id AND a.valid @> CAST(:first_seen AS timestamptz) LIMIT 1),
        :type, :cls, CAST(:first_seen AS timestamptz), :last_seen,
        :max_conf, :frames_positive, :frames_window,
        CAST(:image_id AS uuid), CAST(:models AS jsonb))
ON CONFLICT DO NOTHING
RETURNING 1
""")


def parse(node_id: str, doc: dict[str, Any]) -> Event:
    return Event.model_validate(doc).expect_node(node_id)


async def store(conn: AsyncConnection, e: Event) -> Stored:
    b = e.event
    first_seen = b.first_seen or e.sent_at
    params = {
        "msg_id": str(e.msg_id),
        "episode_id": str(b.episode_id or e.msg_id),
        "node_id": e.node_id,
        "type": b.type,
        "cls": b.cls,
        "first_seen": first_seen,
        "last_seen": b.last_seen or first_seen,
        "max_conf": b.max_conf,
        "frames_positive": b.frames_positive,
        "frames_window": b.frames_window,
        "image_id": str(b.image_id) if b.image_id else None,
        "models": None if b.models is None else json.dumps(b.models),
    }
    if (await conn.execute(_INSERT, params)).first() is None:
        return Stored(str(e.msg_id), 1, 0)
    notify = {"kind": "event", "node_id": e.node_id, "msg_id": str(e.msg_id), "type": b.type, "cls": b.cls}
    return Stored(str(e.msg_id), 1, 1, notify)


HANDLER = Handler("events", parse, store)
