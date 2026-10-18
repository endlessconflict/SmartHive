"""Live feed: PostgreSQL NOTIFY in, JSON out to the sockets that may see it. No web framework here."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from smarthive.alerts.store import ALERT_CHANNEL
from smarthive.ingest.handler import CHANNEL

log = logging.getLogger("smarthive.live")
QUEUE_SIZE = 100


@dataclass(eq=False)
class Subscriber:
    """One socket. `queue` is drained by the route; a full queue means a client too slow to follow."""

    admin: bool
    hives: set[str] = field(default_factory=set)
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(QUEUE_SIZE))
    overflowed: bool = False


def messages(channel: str, n: dict[str, Any]) -> list[tuple[str | None, dict[str, Any]]]:
    """(hive id, message) pairs for one notification. A hive of None goes to administrators only."""
    if channel == ALERT_CHANNEL:
        keys = ("alert_id", "state", "severity", "title")
        return [(n.get("hive_id"), {"type": "alert", **{k: n[k] for k in keys}})]
    kind = n.get("kind")
    if kind == "telemetry":
        out = [(r["hive_id"], {"type": "reading", **r}) for r in n.get("live", [])]
        out += [(h, {"type": "backfill", "hive_id": h}) for h in n.get("backfill", [])]
        return out
    if kind == "event":
        fields = ("hive_id", "node_id", "cls", "first_seen", "image_id")
        return [(n["hive_id"], {"type": "detection", "event": n["type"], **{k: n[k] for k in fields}})]
    if kind == "node_status":
        return [
            (n["hive_id"], {"type": "node_status", **{k: n[k] for k in ("node_id", "status", "hive_id")}})
        ]
    return []


class Hub:
    def __init__(self) -> None:
        self._subscribers: set[Subscriber] = set()

    def add(self, sub: Subscriber) -> None:
        self._subscribers.add(sub)

    def remove(self, sub: Subscriber) -> None:
        self._subscribers.discard(sub)

    def dispatch(self, channel: str, payload: str) -> None:
        try:
            batch = messages(channel, json.loads(payload))
        except (ValueError, KeyError, TypeError):
            log.warning("bad_notification", extra={"fields": {"channel": channel}})
            return
        for hive_id, message in batch:
            for sub in self._subscribers:
                if (hive_id in sub.hives) or (hive_id is None and sub.admin):
                    try:
                        sub.queue.put_nowait(message)
                    except asyncio.QueueFull:
                        sub.overflowed = (
                            True  # the route closes the socket; the client reconnects and refetches
                        )

    def resync(self) -> None:
        """Notifications may have been missed while LISTEN was down: clients refetch everything."""
        for sub in self._subscribers:
            try:
                sub.queue.put_nowait({"type": "resync"})
            except asyncio.QueueFull:
                sub.overflowed = True


async def keep_listening(db_url: str, hub: Hub, retry_s: float = 5) -> None:
    """One LISTEN connection for the whole API process, reopened when it drops. Cancel to stop."""
    first = True
    while True:
        conn: asyncpg.Connection | None = None
        try:
            conn = await asyncpg.connect(db_url.replace("+asyncpg", ""))
            lost = asyncio.Event()
            conn.add_termination_listener(lambda _c, ev=lost: ev.set())
            for channel in (CHANNEL, ALERT_CHANNEL):
                await conn.add_listener(channel, lambda _c, _pid, ch, payload: hub.dispatch(ch, payload))
            if not first:
                hub.resync()
            first = False
            await lost.wait()
            log.warning("listen_connection_lost")
        except (OSError, asyncpg.PostgresError):
            log.exception("listen_failed")
        finally:
            if conn is not None and not conn.is_closed():
                await conn.close()
        await asyncio.sleep(retry_s)
