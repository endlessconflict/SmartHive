"""Nightly housekeeping: drop old data, back up the database, and prove a backup restores."""

import asyncio
import json
import logging
import shutil
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.thumbnails import WIDTHS

log = logging.getLogger("smarthive.maintenance")

HEALTH_KEEP = timedelta(days=90)
# Compared between the live database and a restored copy. Tables that only ever grow, so a restore can
# not legitimately hold fewer rows than were counted just before the dump.
CHECKED_TABLES = (
    "users",
    "apiaries",
    "hives",
    "nodes",
    "node_assignments",
    "readings",
    "detection_events",
    "alerts",
    "images",
)


def tool(name: str) -> str:
    """A PostgreSQL client program: on the PATH, else the newest Debian package directory."""
    found = shutil.which(name)
    if found:
        return found
    packaged = sorted(Path("/usr/lib/postgresql").glob(f"*/bin/{name}"), key=lambda p: int(p.parts[-3]))
    if packaged:
        return str(packaged[-1])
    raise RuntimeError(f"{name} not found: install the PostgreSQL client tools")


def libpq_url(db_url: str) -> str:
    return db_url.replace("+asyncpg", "")


async def purge(engine: AsyncEngine, image_dir: Path, now: datetime | None = None) -> dict[str, int]:
    """Drop `node_health` chunks older than 90 days and images past `expires_at`, files included.

    drop_chunks() is in the Apache-2.0 TimescaleDB; only the automatic retention policy is not.
    """
    now = now or datetime.now(UTC)
    async with engine.begin() as conn:
        chunks = (
            await conn.execute(
                text("SELECT drop_chunks('node_health', older_than => CAST(:t AS timestamptz))"),
                {"t": now - HEALTH_KEEP},
            )
        ).all()
        expired = (
            await conn.execute(
                text("DELETE FROM images WHERE expires_at < CAST(:t AS timestamptz) RETURNING path"),
                {"t": now},
            )
        ).all()
        # files are named after their content, so two rows can share one; keep it while any row uses it
        paths = {r.path for r in expired}
        in_use = set()
        if paths:
            rows = await conn.execute(
                text("SELECT path FROM images WHERE path = ANY(:p)"), {"p": list(paths)}
            )
            in_use = {r.path for r in rows}
    removed = 0
    for rel in paths - in_use:
        try:
            (image_dir / rel).unlink()
            removed += 1
        except FileNotFoundError:
            pass
        for w in WIDTHS:  # cached thumbnails go with the original
            (image_dir / "thumbs" / str(w) / Path(rel).name).unlink(missing_ok=True)
    return {"health_chunks": len(chunks), "images": len(expired), "files": removed}


async def counts(db_url: str) -> dict[str, int]:
    conn = await asyncpg.connect(libpq_url(db_url))
    try:
        return {t: await conn.fetchval(f"SELECT count(*) FROM {t}") for t in CHECKED_TABLES}  # noqa: S608
    finally:
        await conn.close()


def prune(directory: Path, keep: int) -> list[Path]:
    """Delete all but the newest `keep` dumps (and their count files). Names sort by time."""
    dumps = sorted(directory.glob("smarthive-*.dump"))
    old = dumps[:-keep] if keep > 0 else dumps
    for d in old:
        d.unlink()
        d.with_suffix(".json").unlink(missing_ok=True)
    return old


async def backup(db_url: str, directory: Path, keep: int = 14, now: datetime | None = None) -> Path:
    """pg_dump in custom format, plus the row counts taken just before it. Needs pg_dump on the PATH."""
    now = now or datetime.now(UTC)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"smarthive-{now:%Y%m%d-%H%M%S}.dump"
    before = await counts(db_url)
    done = await asyncio.to_thread(
        subprocess.run,
        [tool("pg_dump"), "--format=custom", "--file", str(target), libpq_url(db_url)],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump failed: {done.stderr.strip()[:500]}")
    target.with_suffix(".json").write_text(json.dumps(before))
    prune(directory, keep)
    return target


async def restore_check(db_url: str, dump: Path) -> dict[str, tuple[int, int]]:
    """Restore `dump` into a scratch database and compare row counts with the ones saved beside it.

    Returns {table: (expected at least, restored)}. Raises if any table came back short. The scratch
    database is dropped afterwards.
    """
    expected: dict[str, int] = json.loads(dump.with_suffix(".json").read_text())
    base = libpq_url(db_url)
    name = f"restore_check_{uuid.uuid4().hex[:8]}"
    scratch = base.rsplit("/", 1)[0] + "/" + name
    admin = await asyncpg.connect(base)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        try:
            conn = await asyncpg.connect(scratch)
            try:  # TimescaleDB needs its catalog switched off while a dump is loaded
                await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                await conn.execute("SELECT timescaledb_pre_restore()")
            finally:
                await conn.close()
            done = await asyncio.to_thread(
                subprocess.run,
                [tool("pg_restore"), "--no-owner", "--dbname", scratch, str(dump)],
                capture_output=True,
                text=True,
            )
            if done.returncode != 0:
                raise RuntimeError(f"pg_restore failed: {done.stderr.strip()[:500]}")
            conn = await asyncpg.connect(scratch)
            try:
                await conn.execute("SELECT timescaledb_post_restore()")
            finally:
                await conn.close()
            restored = await counts(scratch.replace("postgresql://", "postgresql+asyncpg://"))
        finally:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()
    result = {t: (expected[t], restored[t]) for t in expected}
    short = {t: v for t, v in result.items() if v[1] < v[0]}
    if short:
        raise RuntimeError(f"restore is missing rows: {short}")
    return result
