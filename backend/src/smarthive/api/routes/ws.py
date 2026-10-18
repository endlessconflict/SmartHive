"""GET /api/v1/ws: live updates. The token goes in the first message, never in the URL."""

import asyncio
import contextlib
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from smarthive.api.deps import Db
from smarthive.api.live import Hub, Subscriber
from smarthive.api.security import InvalidToken, decode_access_token

router = APIRouter()
AUTH_TIMEOUT_S = 10
MAX_HIVES = 200
UNAUTHENTICATED = 4401  # application close codes sit in 4000-4999
SLOW_CLIENT = 4408

_VISIBLE = text(
    "SELECT h.id FROM hives h JOIN apiaries a ON a.id = h.apiary_id "
    "WHERE h.id = ANY(CAST(:ids AS uuid[])) AND (:admin OR a.owner_id = :me)"
)


async def _authenticate(socket: WebSocket) -> tuple[UUID, bool] | None:
    """(user id, is admin) for a first message {"op": "auth", "token": ...}, else None."""
    try:
        msg = await asyncio.wait_for(socket.receive_json(), AUTH_TIMEOUT_S)
        claims = decode_access_token(socket.app.state.settings.jwt_secret, msg["token"])
        if msg.get("op") != "auth":
            return None
    except (TimeoutError, InvalidToken, KeyError, TypeError, ValueError):
        return None
    db = Db(socket.app.state.engine)
    try:
        found = (
            await db.execute(text("SELECT role FROM users WHERE id = :id"), {"id": claims.user_id})
        ).first()
    finally:
        await db.finish(commit=False)
    return (claims.user_id, found.role == "admin") if found else None


async def _visible(socket: WebSocket, user_id: UUID, admin: bool, wanted: Any) -> list[str]:
    """The hive ids among `wanted` the user may see. The others are dropped without a word."""
    if not isinstance(wanted, list):
        return []
    try:
        ids = [str(UUID(str(h))) for h in wanted[:MAX_HIVES]]
    except ValueError:
        return []
    db = Db(socket.app.state.engine)
    try:
        rows = (await db.execute(_VISIBLE, {"ids": ids, "admin": admin, "me": user_id})).all()
    finally:
        await db.finish(commit=False)
    return [str(r.id) for r in rows]


async def _pump(socket: WebSocket, sub: Subscriber) -> None:
    while True:
        message = await sub.queue.get()
        await socket.send_json(message)
        if sub.overflowed:  # messages were dropped: close, the client reconnects and refetches
            await socket.close(SLOW_CLIENT)
            return


@router.websocket("/api/v1/ws")
async def live(socket: WebSocket) -> None:
    await socket.accept()
    who = await _authenticate(socket)
    if who is None:
        await socket.close(UNAUTHENTICATED)
        return
    user_id, admin = who
    hub: Hub = socket.app.state.hub
    sub = Subscriber(admin)
    hub.add(sub)
    pump = asyncio.create_task(_pump(socket, sub))
    try:
        await socket.send_json({"type": "ready"})
        # ponytail: the socket outlives its access token; add a periodic re-auth if that matters
        while not pump.done():
            msg = await socket.receive_json()
            if isinstance(msg, dict) and msg.get("op") == "subscribe":
                sub.hives = set(await _visible(socket, user_id, admin, msg.get("hives")))
                await socket.send_json({"type": "subscribed", "hives": sorted(sub.hives)})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        hub.remove(sub)
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pump
