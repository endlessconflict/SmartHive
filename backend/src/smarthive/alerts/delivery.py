"""Sends the `pending` email and ntfy notifications the alert engine wrote.

Each notification is handled in its own transaction with `FOR UPDATE SKIP LOCKED`, so two workers never
send the same one. A failure waits 1, 2, 4 ... minutes and gives up as `failed` after `notify_max_attempts`.
"""

import asyncio
import logging
import smtplib
import urllib.request
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.deps import Db
from smarthive.config import Settings

log = logging.getLogger("smarthive.delivery")

_DUE = text(
    "SELECT n.id FROM notifications n WHERE n.status = 'pending' AND n.channel = ANY(:channels) "
    "AND (n.next_attempt_at IS NULL OR n.next_attempt_at <= CAST(:now AS timestamptz)) ORDER BY n.id LIMIT 50"
)
_CLAIM = text(
    "SELECT n.id, n.channel, n.attempts, n.user_id, u.email, u.ntfy_topic, "
    "a.title, a.severity, a.rule_id, a.details, a.opened_at, h.name AS hive_name "
    "FROM notifications n JOIN users u ON u.id = n.user_id JOIN alerts a ON a.id = n.alert_id "
    "LEFT JOIN hives h ON h.id = a.hive_id "
    "WHERE n.id = :id AND n.status = 'pending' FOR UPDATE OF n SKIP LOCKED"
)
_RECENT = text(
    "SELECT count(*) FROM notifications WHERE user_id = :u AND channel = :c AND status = 'sent' "
    "AND sent_at > CAST(:now AS timestamptz) - interval '1 hour'"
)


def _body(row: Any) -> str:
    where = f" on hive {row.hive_name}" if row.hive_name else ""
    return f"{row.title}{where}\nSeverity: {row.severity}\nRule: {row.rule_id}\nOpened: {row.opened_at:%Y-%m-%d %H:%M UTC}"


def _send_email(settings: Settings, row: Any) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, row.email, f"[SmartHive] {row.title}"
    msg.set_content(_body(row))
    assert settings.smtp_host
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(msg)


def _send_ntfy(settings: Settings, row: Any) -> None:
    assert settings.ntfy_url
    req = urllib.request.Request(
        f"{settings.ntfy_url.rstrip('/')}/{quote(row.ntfy_topic, safe='')}",
        data=_body(row).encode(),
        headers={"Title": row.title, "Priority": "urgent" if row.severity == "critical" else "default"},
    )
    urllib.request.urlopen(req, timeout=15).close()  # noqa: S310  (the URL is operator configuration)


def enabled_channels(settings: Settings) -> list[str]:
    return [c for c, on in (("email", settings.smtp_host), ("ntfy", settings.ntfy_url)) if on]


async def deliver_pending(engine: AsyncEngine, settings: Settings, now: datetime | None = None) -> int:
    """Try every due notification once. Returns how many were sent."""
    now = now or datetime.now(UTC)
    channels = enabled_channels(settings)
    if not channels:
        return 0
    async with engine.connect() as c:
        ids = [r.id for r in (await c.execute(_DUE, {"channels": channels, "now": now})).all()]
    sent = 0
    for nid in ids:
        db = Db(engine)
        try:
            sent += await _deliver_one(db, settings, nid, now)
        except Exception:
            await db.finish(commit=False)
            log.exception("delivery_crashed", extra={"fields": {"notification": nid}})
        else:
            await db.finish(commit=True)
    return sent


async def _deliver_one(db: Db, settings: Settings, nid: int, now: datetime) -> int:
    row = (await db.execute(_CLAIM, {"id": nid})).first()
    if row is None:  # another worker has it, or it is no longer pending
        return 0
    recent = (await db.execute(_RECENT, {"u": row.user_id, "c": row.channel, "now": now})).scalar_one()
    if recent >= settings.notify_per_user_per_hour:
        await _finish(db, nid, "suppressed", row.attempts, "rate limited", now)
        return 0
    try:
        await asyncio.to_thread(_send_email if row.channel == "email" else _send_ntfy, settings, row)
    except Exception as e:
        attempts = row.attempts + 1
        if attempts >= settings.notify_max_attempts:
            await _finish(db, nid, "failed", attempts, str(e)[:500], now)
        else:
            retry = now + timedelta(minutes=2 ** (attempts - 1))
            await db.execute(
                text(
                    "UPDATE notifications SET attempts = :a, error = :e, next_attempt_at = CAST(:r AS timestamptz) "
                    "WHERE id = :id"
                ),
                {"a": attempts, "e": str(e)[:500], "r": retry, "id": nid},
            )
        log.warning("delivery_failed", extra={"fields": {"notification": nid, "attempts": attempts}})
        return 0
    await _finish(db, nid, "sent", row.attempts + 1, None, now)
    return 1


async def _finish(db: Db, nid: int, status: str, attempts: int, error: str | None, now: datetime) -> None:
    await db.execute(
        text(
            "UPDATE notifications SET status = :s, attempts = :a, error = :e, next_attempt_at = NULL, "
            "sent_at = CASE WHEN :s = 'sent' THEN CAST(:now AS timestamptz) END WHERE id = :id"
        ),
        {"s": status, "a": attempts, "e": error, "now": now, "id": nid},
    )
