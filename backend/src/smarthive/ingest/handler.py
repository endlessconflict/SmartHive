"""Validate one node message and store it. No MQTT in here, so it is easy to test."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from smarthive.contracts.common import NodeMismatch
from smarthive.ingest.base import Handler, Rejected, Result
from smarthive.ingest.handlers import HANDLERS

MAX_PAYLOAD_BYTES = 256 * 1024
CHANNEL = "smarthive_ingest"  # LISTEN/NOTIFY channel for the worker and the WebSocket feed
_TOPIC = re.compile(r"^smarthive/v1/nodes/([A-Za-z0-9._-]{1,64})/([a-z]+)$")

log = logging.getLogger("smarthive.ingest")


@dataclass(frozen=True)
class Parsed:
    handler: Handler
    node_id: str
    message: Any


def validate(topic: str, payload: bytes) -> Parsed:
    """All or nothing: one failed rule rejects the whole message, so a re-sent message means the same."""
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise Rejected("payload_too_large")
    match = _TOPIC.match(topic)
    handler = HANDLERS.get(match[2]) if match else None
    if match is None or handler is None:
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
        message = handler.parse(match[1], doc)
    except ValidationError as e:
        errors = [{"loc": ".".join(map(str, err["loc"])), "msg": err["msg"]} for err in e.errors()[:5]]
        raise Rejected("schema_violation", errors, msg_id if isinstance(msg_id, str) else None) from None
    except NodeMismatch as e:
        raise Rejected("node_id_mismatch", msg_id=str(e.msg_id)) from None
    return Parsed(handler, match[1], message)


# The first message from an unknown node registers it. `simulated` follows the id, never the payload, so a
# simulator can not pass for a real node. Only a live signal (health) may set the node online; a queued
# message delivered late proves nothing, and a `status` message is applied by its own handler.
_REGISTER = text("INSERT INTO nodes (id, is_simulated) VALUES (:id, :sim) ON CONFLICT (id) DO NOTHING")
_SEEN = text(
    "INSERT INTO nodes (id, is_simulated, last_seen_at) VALUES (:id, :sim, now()) "
    "ON CONFLICT (id) DO UPDATE SET last_seen_at = now()"
)
_ONLINE = text(
    "INSERT INTO nodes (id, is_simulated, status, last_seen_at) VALUES (:id, :sim, 'online', now()) "
    "ON CONFLICT (id) DO UPDATE SET status = 'online', last_seen_at = now()"
)
_LIVENESS = {"none": _REGISTER, "seen": _SEEN, "online": _ONLINE}


async def touch_node(conn: AsyncConnection, node_id: str, liveness: str) -> None:
    await conn.execute(_LIVENESS[liveness], {"id": node_id, "sim": node_id.startswith("sim-")})


def _fields(**fields: object) -> dict[str, dict[str, object]]:
    return {"fields": fields}


async def ingest(engine: AsyncEngine, topic: str, payload: bytes) -> Result | None:
    """Validate and store. A rejected message is logged and returns None; database errors propagate."""
    try:
        parsed = validate(topic, payload)
    except Rejected as e:
        log.warning(
            "message_rejected",
            extra=_fields(
                topic=topic,
                reason=e.reason,
                errors=e.errors,
                msg_id=e.msg_id,
                payload=payload[:200].decode("utf-8", "replace"),
            ),
        )
        return None
    async with engine.begin() as conn:  # one transaction: node, rows and NOTIFY commit together or not at all
        await touch_node(conn, parsed.node_id, parsed.handler.liveness)
        stored = await parsed.handler.store(conn, parsed.message)
        if stored.notify:
            await conn.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": CHANNEL, "payload": json.dumps(stored.notify)},
            )
    result = Result(parsed.handler.kind, parsed.node_id, stored)
    log.info(
        "message_ingested",
        extra=_fields(
            kind=result.kind,
            node_id=result.node_id,
            msg_id=stored.msg_id,
            items=stored.items,
            inserted=stored.inserted,
            duplicates=stored.duplicates,
        ),
    )
    return result
