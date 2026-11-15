"""Device tokens handed out over MQTT, so a node gets its image-upload token without anyone copying it.

A node publishes on `smarthive/v1/nodes/<id>/token/req`; the broker's ACL only lets the holder of the <id>
certificate do that, so the request itself proves who is asking. The ingestor stores the hash of a new token
(the old one stops working) and answers on `smarthive/v1/nodes/<id>/token`, which only that node may read.
A node that never talked before is registered on the way, like any first message.
"""

import json
import re
import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.security import hash_refresh_token
from smarthive.ingest.handlers import TOPIC_PREFIX

REQUEST_FILTER = f"{TOPIC_PREFIX}/+/token/req"
_REQUEST = re.compile(r"^smarthive/v1/nodes/([A-Za-z0-9._-]{1,64})/token/req$")

_ISSUE = text(
    "INSERT INTO nodes (id, is_simulated, device_token_hash, last_seen_at) VALUES (:id, :sim, :h, now()) "
    "ON CONFLICT (id) DO UPDATE SET device_token_hash = :h, last_seen_at = now()"
)


def requester(topic: str) -> str | None:
    """The node id when `topic` is a token request."""
    match = _REQUEST.match(topic)
    return match[1] if match else None


def answer_topic(node_id: str) -> str:
    return f"{TOPIC_PREFIX}/{node_id}/token"


async def issue(engine: AsyncEngine, node_id: str) -> bytes:
    """Store the hash of a new token for the node and return the answer to publish."""
    token = secrets.token_urlsafe(32)
    async with engine.begin() as conn:
        await conn.execute(
            _ISSUE, {"id": node_id, "sim": node_id.startswith("sim-"), "h": hash_refresh_token(token)}
        )
    return json.dumps({"token": token}).encode()
