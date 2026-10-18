"""Email through a real SMTP server (Mailpit), ntfy through a local HTTP server, retries and rate limit."""

import hashlib
import io
import json
import threading
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from smarthive.alerts.delivery import deliver_pending
from smarthive.alerts.engine import evaluate_all
from smarthive.config import Settings
from tests.integration.test_alerts import add_hornet, alerts_of, setup_hive

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def mailpit() -> Iterator[tuple[str, int, int]]:
    with DockerContainer("axllent/mailpit:v1.21").with_exposed_ports(1025, 8025) as c:
        wait_for_logs(c, "accessible via")
        yield c.get_container_host_ip(), int(c.get_exposed_port(1025)), int(c.get_exposed_port(8025))


def inbox(mailpit: tuple[str, int, int]) -> list[dict[str, Any]]:
    host, _, api = mailpit
    with urllib.request.urlopen(f"http://{host}:{api}/api/v1/messages") as r:
        messages: list[dict[str, Any]] = json.load(r)["messages"]
    return messages


@pytest.fixture
def ntfy() -> Iterator[tuple[str, list[tuple[str, str, str]]]]:
    got: list[tuple[str, str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            got.append((self.path, self.headers["Priority"], body))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", got
    server.shutdown()


async def critical_alert(engine: AsyncEngine, ntfy_topic: str | None = None) -> tuple[UUID, UUID]:
    owner, hive, node = await setup_hive(engine)
    if ntfy_topic:
        async with engine.begin() as c:
            await c.execute(
                text("UPDATE users SET ntfy_topic = :t WHERE id = :u"), {"t": ntfy_topic, "u": owner}
            )
    await add_hornet(engine, hive, node)
    await evaluate_all(engine)
    (alert,) = await alerts_of(engine, hive)
    return owner, alert.id


async def statuses(engine: AsyncEngine, alert: UUID) -> dict[str, Any]:
    async with engine.connect() as c:
        rows = await c.execute(
            text("SELECT channel, status, attempts, error FROM notifications WHERE alert_id = :a"),
            {"a": alert},
        )
        return {r.channel: r for r in rows}


async def test_email_and_ntfy_are_delivered(
    engine: AsyncEngine, mailpit: tuple[str, int, int], ntfy: tuple[str, list[tuple[str, str, str]]]
) -> None:
    host, port, _ = mailpit
    _, alert = await critical_alert(engine, "hive alerts")
    settings = Settings(smtp_host=host, smtp_port=port, ntfy_url=ntfy[0])

    assert await deliver_pending(engine, settings) >= 2
    rows = await statuses(engine, alert)
    assert rows["email"].status == "sent" and rows["ntfy"].status == "sent" and rows["app"].status == "sent"
    assert any("[SmartHive]" in m["Subject"] for m in inbox(mailpit))
    path, priority, body = ntfy[1][-1]
    assert path == "/hive%20alerts" and priority == "urgent" and "critical" in body
    assert await deliver_pending(engine, settings) == 0  # nothing left to send


async def test_a_failure_backs_off_and_finally_gives_up(engine: AsyncEngine) -> None:
    _, alert = await critical_alert(engine)
    settings = Settings(smtp_host="127.0.0.1", smtp_port=1, notify_max_attempts=3)  # nothing listens there
    now = datetime.now(UTC)

    await deliver_pending(engine, settings, now)
    first = (await statuses(engine, alert))["email"]
    assert first.status == "pending" and first.attempts == 1 and first.error

    await deliver_pending(engine, settings, now)  # too early: backed off
    assert (await statuses(engine, alert))["email"].attempts == 1

    await deliver_pending(engine, settings, now + timedelta(minutes=5))
    await deliver_pending(engine, settings, now + timedelta(minutes=30))
    last = (await statuses(engine, alert))["email"]
    assert last.status == "failed" and last.attempts == 3


async def test_a_channel_without_a_server_stays_pending(engine: AsyncEngine) -> None:
    _, alert = await critical_alert(engine)
    assert await deliver_pending(engine, Settings()) == 0
    assert (await statuses(engine, alert))["email"].status == "pending"


async def test_per_user_hourly_limit_suppresses_the_rest(
    engine: AsyncEngine, mailpit: tuple[str, int, int]
) -> None:
    host, port, _ = mailpit
    owner, first = await critical_alert(engine)
    # a second critical alert for the same owner
    async with engine.begin() as c:
        second = (
            await c.execute(
                text(
                    "INSERT INTO alerts (id, hive_id, rule_id, severity, state, title, details, dedup_key, opened_at, last_seen_at) "
                    "SELECT gen_random_uuid(), hive_id, 'hornet_detected', 'critical', 'open', 'again', '{}', 'k-' || gen_random_uuid(), now(), now() "
                    "FROM alerts WHERE id = :a RETURNING id"
                ),
                {"a": first},
            )
        ).scalar_one()
        await c.execute(
            text(
                "INSERT INTO notifications (alert_id, user_id, channel, status) VALUES (:a, :u, 'email', 'pending')"
            ),
            {"a": second, "u": owner},
        )
    settings = Settings(smtp_host=host, smtp_port=port, notify_per_user_per_hour=1)
    await deliver_pending(engine, settings)
    sent = (await statuses(engine, first))["email"].status, (await statuses(engine, second))["email"].status
    assert sorted(sent) == ["sent", "suppressed"]


async def test_email_is_multipart_with_the_hive_picture(
    engine: AsyncEngine, mailpit: tuple[str, int, int], tmp_path: Path
) -> None:
    host, port, api = mailpit
    owner, hive, node = await setup_hive(engine)
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (10, 90, 200)).save(buf, "JPEG")
    digest = hashlib.sha256(buf.getvalue()).hexdigest()
    rel = f"{digest}.jpg"
    (tmp_path / rel).write_bytes(buf.getvalue())
    await add_hornet(engine, hive, node)
    async with engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO images (id, node_id, hive_id, captured_at, clock_synced, reason, path, sha256, bytes, objects, expires_at) "
                "VALUES (gen_random_uuid(), :n, :h, now(), true, 'threat', :p, :s, :b, '[]', now() + interval '1 day')"
            ),
            {"n": node, "h": hive, "p": rel, "s": digest, "b": len(buf.getvalue())},
        )
    await evaluate_all(engine)
    settings = Settings(smtp_host=host, smtp_port=port, image_dir=str(tmp_path))

    assert await deliver_pending(engine, settings) >= 1
    summary = inbox(mailpit)[0]
    with urllib.request.urlopen(f"http://{host}:{api}/api/v1/message/{summary['ID']}") as r:
        message = json.load(r)
    assert "<img" in message["HTML"] and "cid:alert-image" in message["HTML"]
    assert message["Text"].startswith("Hornet") or "Severity: critical" in message["Text"]
    assert len(message["Inline"]) == 1 and message["Inline"][0]["ContentType"] == "image/jpeg"
