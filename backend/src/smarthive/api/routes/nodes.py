"""Node registry: an admin adds nodes and decides which hive each one is attached to.

A node gets its image-upload token by itself over MQTT (smarthive/ingest/device_token.py), so registering
it is all an admin does. `POST /nodes/{id}/device-token` is there for testing the upload by hand.
"""

import secrets
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from smarthive.api.deps import Admin, Conn
from smarthive.api.errors import Problem
from smarthive.api.security import hash_refresh_token

router = APIRouter(tags=["nodes"])

NodeId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")]
_COLUMNS = (
    "id, is_simulated AS simulated, status, last_seen_at, registered_at, "
    "COALESCE(device_token_hash, '') <> '' AS has_token"
)
_NODE = (
    f"SELECT {_COLUMNS}, "
    "(SELECT hive_id FROM node_assignments a WHERE a.node_id = n.id AND a.valid @> now() LIMIT 1) AS hive_id "
    "FROM nodes n"
)


class Node(BaseModel):
    id: str
    simulated: bool
    status: str
    last_seen_at: datetime | None
    registered_at: datetime
    has_token: bool
    hive_id: UUID | None


class NodeIn(BaseModel):
    id: NodeId


class IssuedToken(BaseModel):
    node_id: str
    device_token: str  # shown once; only its hash is stored


class Assignment(BaseModel):
    hive_id: UUID
    valid_from: datetime | None = None  # default: now. Readings from this moment on belong to the hive.


async def _node(conn: Conn, node_id: str) -> Node:
    row = (await conn.execute(text(f"{_NODE} WHERE n.id = :id"), {"id": node_id})).first()
    if row is None:
        raise Problem(404, "Node not found")
    return Node(**row._mapping)


@router.get("/api/v1/nodes", response_model=list[Node], summary="All nodes")
async def list_nodes(conn: Conn, _: Admin) -> list[Node]:
    return [Node(**r._mapping) for r in (await conn.execute(text(f"{_NODE} ORDER BY n.id"))).all()]


@router.post("/api/v1/nodes", response_model=Node, status_code=201, summary="Register a node")
async def register_node(body: NodeIn, conn: Conn, _: Admin) -> Node:
    """Adds the node; a node that already talked over MQTT exists, and the call just returns it.

    The node asks for its device token over MQTT the first time it needs one; nothing to copy.
    """
    await conn.execute(
        text("INSERT INTO nodes (id, is_simulated) VALUES (:id, :sim) ON CONFLICT (id) DO NOTHING"),
        {"id": body.id, "sim": body.id.startswith("sim-")},
    )
    return await _node(conn, body.id)


@router.post(
    "/api/v1/nodes/{node_id}/device-token",
    response_model=IssuedToken,
    summary="Issue a new device token by hand (testing)",
)
async def issue_device_token(node_id: str, conn: Conn, _: Admin) -> IssuedToken:
    """Replaces the node's token, for uploading images from Postman. The real node gets its own over MQTT,
    and asks again (replacing this one) when the API refuses its old one."""
    await _node(conn, node_id)
    token = secrets.token_urlsafe(32)
    await conn.execute(
        text("UPDATE nodes SET device_token_hash = :h WHERE id = :id"),
        {"id": node_id, "h": hash_refresh_token(token)},
    )
    return IssuedToken(node_id=node_id, device_token=token)


@router.get("/api/v1/nodes/{node_id}", response_model=Node, summary="One node")
async def get_node(node_id: str, conn: Conn, _: Admin) -> Node:
    return await _node(conn, node_id)


@router.post("/api/v1/nodes/{node_id}/assign", response_model=Node, summary="Attach a node to a hive")
async def assign_node(node_id: str, body: Assignment, conn: Conn, _: Admin) -> Node:
    await _node(conn, node_id)
    hive = (await conn.execute(text("SELECT 1 FROM hives WHERE id = :h"), {"h": body.hive_id})).first()
    if hive is None:
        raise Problem(404, "Hive not found")
    params = {"n": node_id, "h": body.hive_id, "from": body.valid_from}
    try:
        await conn.execute(
            text(
                "INSERT INTO node_assignments (node_id, hive_id, valid) "
                "VALUES (:n, :h, tstzrange(COALESCE(CAST(:from AS timestamptz), now()), NULL))"
            ),
            params,
        )
    except (
        IntegrityError
    ):  # the exclusion constraint: the node, or its new range, overlaps another assignment
        raise Problem(409, "Node is already assigned to a hive in that period; unassign it first") from None
    # Rows stored while the node had no hive stay unattributed until now.
    for table, column in (
        ("readings", "ts"),
        ("detection_events", "first_seen"),
        ("images", "captured_at"),
        ("vision_summaries", "window_start"),
    ):
        await conn.execute(
            text(
                f"UPDATE {table} SET hive_id = :h WHERE node_id = :n AND hive_id IS NULL "
                f"AND {column} >= COALESCE(CAST(:from AS timestamptz), now())"
            ),
            params,
        )
    return await _node(conn, node_id)


@router.post("/api/v1/nodes/{node_id}/unassign", response_model=Node, summary="Detach a node from its hive")
async def unassign_node(node_id: str, conn: Conn, _: Admin) -> Node:
    await _node(conn, node_id)
    done = await conn.execute(
        text(
            "UPDATE node_assignments SET valid = tstzrange(lower(valid), now()) "
            "WHERE node_id = :n AND valid @> now() AND upper_inf(valid)"
        ),
        {"n": node_id},
    )
    if done.rowcount == 0:
        raise Problem(409, "Node is not assigned to a hive")
    return await _node(conn, node_id)
