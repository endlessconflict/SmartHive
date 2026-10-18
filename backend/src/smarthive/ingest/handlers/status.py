"""Retained online/offline state, including the last will. The message is the status itself."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from smarthive.contracts.status import Status
from smarthive.ingest.base import Handler, Stored

# The broker redelivers the retained message whenever the ingestor reconnects. Setting the state a node
# already has changes nothing, so `inserted` counts real changes only.
_APPLY = text(
    "UPDATE nodes SET status = :state WHERE id = :node_id AND status IS DISTINCT FROM :state RETURNING 1"
)


class ParsedStatus:
    def __init__(self, node_id: str, status: Status) -> None:
        self.node_id = node_id
        self.status = status


def parse(node_id: str, doc: dict[str, Any]) -> ParsedStatus:
    # no node_id in this payload: the topic, and behind it the certificate, is the identity
    return ParsedStatus(node_id, Status.model_validate(doc))


async def store(conn: AsyncConnection, p: ParsedStatus) -> Stored:
    changed = (
        await conn.execute(_APPLY, {"state": p.status.state, "node_id": p.node_id})
    ).first() is not None
    notify = {"kind": "node_status", "node_id": p.node_id, "status": p.status.state} if changed else None
    return Stored(None, 1, 1 if changed else 0, notify)


HANDLER = Handler("status", parse, store, liveness="none")
