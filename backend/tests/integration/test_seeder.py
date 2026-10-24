"""Seeder output goes through the real ingest path into a real TimescaleDB."""

import json
import random
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive import seeder
from smarthive.ingest.handler import ingest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["normal", "hornet", "varroa", "low-battery"])
async def test_every_seeded_message_is_stored(engine: AsyncEngine, scenario: str) -> None:
    for kind, payload, _ in seeder.messages(
        "node-0001", "boot-1", datetime.now(UTC), scenario, random.Random(7)
    ):
        result = await ingest(engine, f"smarthive/v1/nodes/node-0001/{kind}", json.dumps(payload).encode())
        assert result is not None, f"{kind} was rejected"
    async with engine.connect() as conn:
        readings = (await conn.execute(text("SELECT count(*) FROM readings"))).scalar_one()
        events = (await conn.execute(text("SELECT count(*) FROM detection_events"))).scalar_one()
    assert readings == 15  # 5 quantities x 3 timestamps
    assert events == (1 if scenario == "hornet" else 0)
