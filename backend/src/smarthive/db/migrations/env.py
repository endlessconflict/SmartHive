"""Alembic environment, async (asyncpg). The URL comes from SMARTHIVE_DB_URL."""

import asyncio

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from smarthive.config import Settings


def _run(connection: Connection) -> None:
    # No ORM metadata: migrations are raw SQL taken from docs/05-backend/05-data-model.md
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_async_engine(Settings().db_url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


asyncio.run(_run_online())
