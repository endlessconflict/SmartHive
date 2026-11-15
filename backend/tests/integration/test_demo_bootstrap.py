"""The demo apiary: what `smarthive demo-bootstrap` writes, and that a second run leaves it alone."""

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive import demo_bootstrap
from smarthive.api.app import create_app
from smarthive.config import Settings
from tests.integration.test_api_auth import SECRET

pytestmark = pytest.mark.integration

PASSWORD = "a-long-demo-password"


async def count(engine: AsyncEngine, sql: str) -> int:
    async with engine.connect() as c:
        return int((await c.execute(text(sql))).scalar_one())


async def test_bootstrap_writes_a_week_and_is_idempotent(engine: AsyncEngine) -> None:
    assert await demo_bootstrap.run(engine, "demo@example.test", PASSWORD, "Demo")
    assert await count(engine, "SELECT count(*) FROM hives") == 5
    assert await count(engine, "SELECT count(*) FROM node_assignments") == 5
    assert await count(engine, "SELECT count(*) FROM readings") == 5 * 3 * (7 * 144 + 1)
    assert await count(engine, "SELECT count(*) FROM management_events") == 4
    # the humidity drop on hive 3 is already a warning, with no notification behind it
    assert await count(engine, "SELECT count(*) FROM anomalies") >= 1
    assert await count(engine, "SELECT count(*) FROM notifications") == 0

    assert not await demo_bootstrap.run(engine, "demo@example.test", PASSWORD, "Demo")
    assert await count(engine, "SELECT count(*) FROM readings") == 5 * 3 * (7 * 144 + 1)


async def test_bootstrap_account_can_sign_in_and_sees_the_hives(engine: AsyncEngine) -> None:
    await demo_bootstrap.run(engine, "demo@example.test", PASSWORD, "Demo")
    transport = httpx.ASGITransport(app=create_app(Settings(jwt_secret=SECRET), engine))
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        login = await c.post("/api/v1/auth/login", json={"email": "demo@example.test", "password": PASSWORD})
        assert login.status_code == 200
        headers = {"authorization": f"Bearer {login.json()['access_token']}"}
        hives = (await c.get("/api/v1/hives?limit=50", headers=headers)).json()["items"]
    assert len(hives) == 5
    assert all(h["simulated"] and h["latest"]["temp_in"] for h in hives)
