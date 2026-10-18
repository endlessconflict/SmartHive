"""Email through a real SMTP server (Mailpit), ntfy through a local HTTP server, retries and rate limit."""

import json
import threading
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from uuid import UUID

import pytest
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
    assert any(""[SmartHive]" in m["Subject"] for m in inbox(mailpit))
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
