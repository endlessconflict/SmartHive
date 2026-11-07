"""Everything the node sends is written here first, connected or not (docs/05-backend/03-edge-node-software.md).

SQLite in WAL mode: a commit survives the process dying at any moment. With synchronous=NORMAL a power cut can
lose the last seconds of commits, but it does not corrupt the file, and the SD card is flushed far less often.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
  msg_id       TEXT PRIMARY KEY,
  node_id      TEXT NOT NULL,
  kind         TEXT NOT NULL,
  topic        TEXT NOT NULL,
  payload      BLOB NOT NULL,
  created_at   INTEGER NOT NULL,
  clock_synced INTEGER NOT NULL,
  priority     INTEGER NOT NULL,
  attempts     INTEGER NOT NULL DEFAULT 0,
  sent_at      INTEGER
);
CREATE INDEX IF NOT EXISTS outbox_pending ON outbox (sent_at, priority);
"""
_PRIORITY = {"events": 0, "telemetry": 1, "health": 2}  


@dataclass(frozen=True)
class Row:
    msg_id: str
    node_id: str
    kind: str
    topic: str
    payload: bytes
    created_at: int  
    clock_synced: bool


class Outbox:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, isolation_level=None)  
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_SCHEMA)

    def add(self, topic: str, payload: bytes, created_at: datetime, clock_synced: bool) -> None:
        """Store one message exactly as it will be sent, so a re-send keeps its msg_id and the server drops it."""
        envelope = json.loads(payload)
        kind = topic.rsplit("/", 1)[-1]
        self._db.execute(
            "INSERT INTO outbox (msg_id, node_id, kind, topic, payload, created_at, clock_synced, priority) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (envelope["msg_id"], envelope["node_id"], kind, topic, payload, int(created_at.timestamp() * 1000),
             clock_synced, _PRIORITY.get(kind, 1)),
        )

    def pending(self, limit: int = 100) -> list[Row]:
        """Oldest first within each priority. By write order, not created_at: without an RTC, the clock can jump."""
        rows = self._db.execute(
            "SELECT msg_id, node_id, kind, topic, payload, created_at, clock_synced FROM outbox "
            "WHERE sent_at IS NULL ORDER BY priority, rowid LIMIT ?",
            (limit,),
        )
        return [Row(r[0], r[1], r[2], r[3], r[4], r[5], bool(r[6])) for r in rows]

    def mark_sent(self, msg_id: str, at: datetime | None = None) -> None:
        at = at or datetime.now(UTC)
        self._db.execute("UPDATE outbox SET sent_at = ? WHERE msg_id = ?", (int(at.timestamp() * 1000), msg_id))

    def mark_failed(self, msg_id: str) -> None:
        self._db.execute("UPDATE outbox SET attempts = attempts + 1 WHERE msg_id = ?", (msg_id,))

    def purge(self, older_than: datetime) -> int:
        """Delete rows sent before that time. Unsent rows stay, however old: they are the point of the outbox."""
        cursor = self._db.execute(
            "DELETE FROM outbox WHERE sent_at IS NOT NULL AND sent_at < ?", (int(older_than.timestamp() * 1000),)
        )
        return cursor.rowcount

    def close(self) -> None:
        self._db.close()
