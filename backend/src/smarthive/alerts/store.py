"""Alert rows: open once per key, touch while the condition holds, move through the lifecycle, notify."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from smarthive.api.deps import Db
from smarthive.ingest.handler import CHANNEL  # noqa: F401  (re-exported for the worker)

ALERT_CHANNEL = "smarthive_alerts"  # the WebSocket feed; the worker listens to CHANNEL only, so no loop
_RANK = {"info": 0, "warning": 1, "critical": 2}
COOLDOWN_HOURS = 6  # a condition a user resolved by hand does not reopen right away
# ponytail: one cooldown for every rule, per-rule setting if beekeepers want different quiet periods


@dataclass(frozen=True)
class Finding:
    """A condition a rule found true right now."""

    rule_id: str
    dedup_key: str
    title: str
    details: dict[str, Any] = field(default_factory=dict)
    hive_id: UUID | None = None
    node_id: str | None = None
    severity: str | None = None  # overrides the rule's stored severity, e.g. an escalated node_offline


async def raise_alert(
    conn: Db, severity: str, f: Finding, now: datetime, *, once: bool = False
) -> UUID | None:
    """Open an alert, or refresh the open one with the same key. Returns the id only for a new alert.

    `once`: the key names one occurrence (a detection episode), so it never reopens, even after resolution.
    """
    touched = await conn.execute(
        text(
            "UPDATE alerts SET last_seen_at = CAST(:now AS timestamptz), details = CAST(:d AS jsonb) "
            "WHERE dedup_key = :k AND state <> 'resolved' RETURNING id, severity"
        ),
        {"now": now, "d": json.dumps(f.details), "k": f.dedup_key},
    )
    open_alert = touched.first()
    if open_alert:
        if f.severity and _RANK[f.severity] > _RANK[open_alert.severity]:
            await conn.execute(
                text("UPDATE alerts SET severity = :s WHERE id = :id"), {"s": f.severity, "id": open_alert.id}
            )
            await _log(
                conn, open_alert.id, "escalated", None, {"from": open_alert.severity, "to": f.severity}
            )
            await _notify(conn, open_alert.id, f.severity, f.hive_id, f.node_id, now)
            await _announce(conn, open_alert.id)
        return None
    blocked = (
        await conn.execute(
            text(
                "SELECT 1 FROM alerts WHERE dedup_key = :k AND (:once OR "
                "(resolved_by IS NOT NULL AND resolved_at > CAST(:now AS timestamptz) - make_interval(hours => :h))) LIMIT 1"
            ),
            {"k": f.dedup_key, "once": once, "now": now, "h": COOLDOWN_HOURS},
        )
    ).first()
    if blocked:
        return None
    severity = f.severity or severity
    alert_id = uuid4()
    row = (
        await conn.execute(
            text(
                "INSERT INTO alerts (id, hive_id, node_id, rule_id, severity, state, title, details, "
                "dedup_key, opened_at, last_seen_at) VALUES (:id, :hive, :node, :rule, :sev, 'open', :title, "
                "CAST(:d AS jsonb), :k, CAST(:now AS timestamptz), CAST(:now AS timestamptz)) ON CONFLICT (dedup_key) WHERE state <> 'resolved' "
                "DO NOTHING RETURNING id"
            ),
            {
                "id": alert_id,
                "hive": f.hive_id,
                "node": f.node_id,
                "rule": f.rule_id,
                "sev": severity,
                "title": f.title,
                "d": json.dumps(f.details),
                "k": f.dedup_key,
                "now": now,
            },
        )
    ).first()
    if row is None:  # another worker opened it between our checks
        return None
    await _log(conn, alert_id, "opened", None, {"severity": severity})
    await _notify(conn, alert_id, severity, f.hive_id, f.node_id, now)
    await _announce(conn, alert_id)
    return alert_id


async def _announce(conn: Db, alert_id: UUID) -> None:
    """Tell the WebSocket feed about an alert's new state; delivered when the transaction commits."""
    await conn.execute(
        text(
            "SELECT pg_notify(:ch, json_build_object('alert_id', a.id, 'state', a.state, 'severity', a.severity, "
            "'title', a.title, 'hive_id', a.hive_id)::text) FROM alerts a WHERE a.id = :id"
        ),
        {"ch": ALERT_CHANNEL, "id": alert_id},
    )


async def _log(conn: Db, alert_id: UUID, kind: str, actor: UUID | None, data: dict[str, Any]) -> None:
    await conn.execute(
        text("INSERT INTO alert_events (alert_id, kind, actor, data) VALUES (:a, :k, :u, CAST(:d AS jsonb))"),
        {"a": alert_id, "k": kind, "u": actor, "d": json.dumps(data)},
    )


async def _notify(
    conn: Db, alert_id: UUID, severity: str, hive_id: UUID | None, node_id: str | None, now: datetime
) -> None:
    """In-app for warning and critical; email and ntfy only for critical and never for simulated nodes.

    Email and ntfy rows are written as `pending`; the delivery worker sends them with retries.
    """
    if severity == "info":
        return
    users = (
        await conn.execute(
            text(
                "SELECT u.id, u.notify_email, u.ntfy_topic FROM users u WHERE "
                "u.id = (SELECT a.owner_id FROM hives h JOIN apiaries a ON a.id = h.apiary_id WHERE h.id = :h) "
                "OR (:h IS NULL AND u.role = 'admin')"
            ),
            {"h": hive_id},
        )
    ).all()
    simulated = bool(
        node_id
        and (
            await conn.execute(text("SELECT is_simulated FROM nodes WHERE id = :n"), {"n": node_id})
        ).scalar()
    )
    for u in users:
        rows = [("app", "sent")]
        if severity == "critical" and not simulated:
            if u.notify_email:
                rows.append(("email", "pending"))
            if u.ntfy_topic:
                rows.append(("ntfy", "pending"))
        for channel, status in rows:
            await conn.execute(
                text(
                    "INSERT INTO notifications (alert_id, user_id, channel, status, sent_at) "
                    "VALUES (:a, :u, :c, :s, CASE WHEN :s = 'sent' THEN CAST(:now AS timestamptz) END)"
                ),
                {"a": alert_id, "u": u.id, "c": channel, "s": status, "now": now},
            )


async def resolve_stale(conn: Db, rule_id: str, live_keys: set[str], now: datetime) -> int:
    """Auto-resolve open alerts of a rule whose condition has cleared."""
    rows = (
        await conn.execute(
            text(
                "UPDATE alerts SET state = 'resolved', resolved_at = CAST(:now AS timestamptz), resolution_note = 'condition cleared' "
                "WHERE rule_id = :r AND state <> 'resolved' AND NOT (dedup_key = ANY(:keys)) RETURNING id"
            ),
            {"r": rule_id, "keys": list(live_keys), "now": now},
        )
    ).all()
    for r in rows:
        await _log(conn, r.id, "auto_resolved", None, {})
        await _announce(conn, r.id)
    return len(rows)


async def transition(conn: Db, alert_id: UUID, to: str, actor: UUID, note: str | None, now: datetime) -> bool:
    """acknowledged: from open. resolved: from open or acknowledged. False when the state does not allow it."""
    if to == "acknowledged":
        sql = (
            "UPDATE alerts SET state = 'acknowledged', acknowledged_at = CAST(:now AS timestamptz), acknowledged_by = :u "
            "WHERE id = :id AND state = 'open'"
        )
    else:
        sql = (
            "UPDATE alerts SET state = 'resolved', resolved_at = CAST(:now AS timestamptz), resolved_by = :u, resolution_note = :note "
            "WHERE id = :id AND state <> 'resolved'"
        )
    done = (
        await conn.execute(
            text(sql + " RETURNING id"), {"id": alert_id, "u": actor, "now": now, "note": note}
        )
    ).first()
    if done:
        await _log(conn, alert_id, to, actor, {"note": note} if note else {})
        await _announce(conn, alert_id)
    return done is not None
