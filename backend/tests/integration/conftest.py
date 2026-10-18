"""Real TimescaleDB (Apache-2.0 "-oss" image) in a container, migrated with Alembic. Needs Docker."""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

BACKEND = Path(__file__).parents[2]
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
        await conn.execute(
            text(
                "TRUNCATE readings, node_health, vision_summaries, detection_events, "
                "node_assignments, nodes, "
                "hives, apiaries, users RESTART IDENTITY CASCADE"
            )
        )
    yield engine
    await engine.dispose()
