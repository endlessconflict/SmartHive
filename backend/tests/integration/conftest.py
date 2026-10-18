"""Real TimescaleDB (Apache-2.0 "-oss" image) in a container, migrated with Alembic. Needs Docker."""

import json
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

BACKEND = Path(__file__).parents[2]
_seeded_rules: list[dict[str, Any]] = []  # alert_rules as the migrations left them
TIMESCALE_IMAGE = "timescale/timescaledb:2.17.2-pg16-oss"


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    with PostgresContainer(TIMESCALE_IMAGE, username="smarthive", password="test", dbname="smarthive") as pg:
        url = (
            f"postgresql+asyncpg://smarthive:test@{pg.get_container_host_ip()}"
            f":{pg.get_exposed_port(5432)}/smarthive"
        )
        previous = os.environ.get("SMARTHIVE_DB_URL")
        os.environ["SMARTHIVE_DB_URL"] = url  # read by migrations/env.py
        try:
            config = Config(str(BACKEND / "alembic.ini"))
            config.set_main_option("script_location", str(BACKEND / "src/smarthive/db/migrations"))
            command.upgrade(config, "head")  # also proves the baseline migration (EN-08.2)
        finally:
            if previous is None:
                del os.environ["SMARTHIVE_DB_URL"]
            else:
                os.environ["SMARTHIVE_DB_URL"] = previous
        yield url


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        if not _seeded_rules:  # first test, before anything is truncated
            rows = await conn.execute(text("SELECT id, severity, params FROM alert_rules"))
            _seeded_rules.extend(dict(r._mapping) for r in rows)
        await conn.execute(
            text(
                "TRUNCATE readings, node_health, vision_summaries, detection_events, "
                "node_assignments, nodes, "
                "hives, apiaries, users RESTART IDENTITY CASCADE"
            )
        )
        # the cascade also emptied alert_rules (it references hives)
        for rule in _seeded_rules:
            await conn.execute(
                text(
                    "INSERT INTO alert_rules (id, severity, params) VALUES (:id, :severity, CAST(:p AS jsonb))"
                ),
                {"id": rule["id"], "severity": rule["severity"], "p": json.dumps(rule["params"])},
            )
    yield engine
    await engine.dispose()
