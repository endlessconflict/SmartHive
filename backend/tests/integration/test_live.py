"""The WebSocket feed end to end: real server, real PostgreSQL NOTIFY, real ingestion."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from smarthive.alerts import store
from smarthive.alerts.store import Finding
from smarthive.api.app import create_app
from smarthive.api.deps import Db
from smarthive.api.security import create_access_token
from smarthive.config import Settings
from smarthive.ingest.handler import ingest
from tests.integration.test_api_auth import SECRET, add_user
from tests.integration.test_ingest_topics import NODE, load, raw, topic

pytestmark = pytest.mark.integration


@pytest.fixture
async def url(engine: AsyncEngine, db_url: str) -> AsyncIterator[str]:
    app = create_app(Settings(jwt_secret=SECRET, db_url=db_url), engine)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)  # the LISTEN connection opens right after startup
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"ws://127.0.0.1:{port}/api/v1/ws"
    server.should_exit = True
    await task


def token(user: UUID, role: str = "beekeeper") -> str:
    return create_access_token(SECRET, user, role, 15)


async def open_socket(url: str, user: UUID, hives: list[str], role: str = "beekeeper") -> ClientConnection:
    ws = await connect(url)
    await ws.send(json.dumps({"op": "auth", "token": token(user, role)}))
    assert json.loads(await ws.recv()) == {"type": "ready"}
    await ws.send(json.dumps({"op": "subscribe", "hives": hives}))
    return ws


async def next_message(ws: ClientConnection, kind: str) -> dict[str, Any]:
    for _ in range(10):
        msg: dict[str, Any] = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if msg["type"] == kind:
            return msg
    raise AssertionError(f"no {kind} message")


async def hive_of(engine: AsyncEngine, owner: UUID, node: str = NODE) -> str:
    async with engine.begin() as conn:
        apiary = (
            await conn.execute(
                text(
                    "INSERT INTO apiaries (id, owner_id, name) VALUES (gen_random_uuid(), :o, 'a') RETURNING id"
                ),
                {"o": owner},
            )
        ).scalar_one()
        hive = (
            await conn.execute(
                text(
                    "INSERT INTO hives (id, apiary_id, name) VALUES (gen_random_uuid(), :a, 'h') RETURNING id"
                ),
                {"a": apiary},
            )
        ).scalar_one()
        await conn.execute(text("INSERT INTO nodes (id, is_simulated) VALUES (:n, false)"), {"n": node})
        await conn.execute(
            text("INSERT INTO node_assignments VALUES (:n, :h, tstzrange('2026-10-01', '2027-11-01'))"),
            {"n": node, "h": hive},
        )
    return str(hive)


async def test_the_token_never_goes_in_the_url_and_a_bad_one_is_refused(url: str) -> None:
    ws = await connect(url + "?token=whatever")
    await ws.send(json.dumps({"op": "auth", "token": "garbage"}))
    with pytest.raises(ConnectionClosed) as closed:
        await ws.recv()
    assert closed.value.rcvd is not None and closed.value.rcvd.code == 4401


async def test_a_live_reading_arrives_and_old_data_becomes_a_backfill_notice(
    url: str, engine: AsyncEngine
) -> None:
    ana = await add_user(engine, f"ana-{uuid4().hex[:6]}@example.com")
    hive = await hive_of(engine, ana)
    ws = await open_socket(url, ana, [hive])
    assert (await next_message(ws, "subscribed"))["hives"] == [hive]

    old = load("telemetry_valid.json")  # readings from days ago: a node that was offline
    await ingest(engine, topic("telemetry"), raw(old))
    assert (await next_message(ws, "backfill"))["hive_id"] == hive

    fresh = load("telemetry_valid.json")
    fresh["msg_id"] = str(uuid4())
    fresh["readings"] = fresh["readings"][:2]  # drop the read_error sample
    for r in fresh["readings"]:
        r["ts"] = datetime.now(UTC).isoformat()
    await ingest(engine, topic("telemetry"), raw(fresh))
    reading = await next_message(ws, "reading")
    assert reading["hive_id"] == hive and reading["quantity"] == "temp_in" and reading["value"] == 35
    await ws.close()


async def test_a_socket_for_a_hive_the_user_cannot_see_receives_nothing(
    url: str, engine: AsyncEngine
) -> None:
    ana = await add_user(engine, f"ana-{uuid4().hex[:6]}@example.com")
    bob = await add_user(engine, f"bob-{uuid4().hex[:6]}@example.com")
    hive = await hive_of(engine, ana)
    spy = await open_socket(url, bob, [hive])
    assert (await next_message(spy, "subscribed"))["hives"] == []
    owner = await open_socket(url, ana, [hive])
    await next_message(owner, "subscribed")

    await ingest(engine, topic("events"), raw(load("event_threat.json")))
    assert (await next_message(owner, "detection"))["cls"] == "hornet"
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(spy.recv(), timeout=1)
    await spy.close()
    await owner.close()


async def test_alerts_and_node_status_changes_are_pushed(url: str, engine: AsyncEngine) -> None:
    ana = await add_user(engine, f"ana-{uuid4().hex[:6]}@example.com")
    hive = await hive_of(engine, ana)
    ws = await open_socket(url, ana, [hive])
    await next_message(ws, "subscribed")

    await ingest(engine, topic("status"), json.dumps({"state": "offline"}).encode())
    status = await next_message(ws, "node_status")
    assert status["status"] == "offline" and status["hive_id"] == hive

    db = Db(engine)
    finding = Finding("hornet", "test-key", "Hornet at the entrance", hive_id=UUID(hive), node_id=NODE)
    await store.raise_alert(db, "critical", finding, datetime.now(UTC))
    await db.finish(commit=True)
    alert = await next_message(ws, "alert")
    assert alert["state"] == "open" and alert["severity"] == "critical"
    await ws.close()
