"""Retention, dump pruning, and the backup/restore round trip, against a real TimescaleDB."""

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive import maintenance
from tests.integration.test_alerts import setup_hive

pytestmark = pytest.mark.integration


async def add_image(engine: AsyncEngine, node: str, path: str, expires: datetime) -> None:
    async with engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO images (id, node_id, captured_at, clock_synced, reason, path, sha256, bytes, expires_at) "
                "VALUES (:i, :n, now(), true, 'periodic', :p, :s, 1, :e)"
            ),
            {"i": uuid4(), "n": node, "p": path, "s": uuid4().hex, "e": expires},
        )


async def test_purge_drops_old_health_and_expired_images_but_keeps_shared_files(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    _, _, node = await setup_hive(engine)
    now = datetime.now(UTC)
    async with engine.begin() as c:
        for age in (200, 1):
            await c.execute(
                text("INSERT INTO node_health (ts, node_id, data) VALUES (:t, :n, '{}')"),
                {"t": now - timedelta(days=age), "n": node},
            )
    for rel in ("aa/old.jpg", "bb/shared.jpg", "cc/fresh.jpg"):
        (tmp_path / rel).parent.mkdir(parents=True)
        (tmp_path / rel).write_bytes(b"x")
    (tmp_path / "thumbs" / "320").mkdir(parents=True)
    (tmp_path / "thumbs" / "320" / "old.jpg").write_bytes(b"x")
    await add_image(engine, node, "aa/old.jpg", now - timedelta(days=1))
    await add_image(engine, node, "bb/shared.jpg", now - timedelta(days=1))
    await add_image(engine, node, "bb/shared.jpg", now + timedelta(days=5))
    await add_image(engine, node, "cc/fresh.jpg", now + timedelta(days=5))

    done = await maintenance.purge(engine, tmp_path, now)
    assert done == {"health_chunks": 1, "images": 2, "files": 1}
    async with engine.connect() as c:
        assert (await c.execute(text("SELECT count(*) FROM node_health"))).scalar_one() == 1
        assert (await c.execute(text("SELECT count(*) FROM images"))).scalar_one() == 2
    assert not (tmp_path / "aa/old.jpg").exists() and not (tmp_path / "thumbs/320/old.jpg").exists()
    assert (tmp_path / "bb/shared.jpg").exists() and (tmp_path / "cc/fresh.jpg").exists()
    assert await maintenance.purge(engine, tmp_path, now) == {"health_chunks": 0, "images": 0, "files": 0}


def test_prune_keeps_the_newest_dumps_and_their_count_files(tmp_path: Path) -> None:
    for day in range(1, 21):
        stem = tmp_path / f"smarthive-202610{day:02d}-030000"
        stem.with_suffix(".dump").write_bytes(b"d")
        stem.with_suffix(".json").write_text("{}")
    removed = maintenance.prune(tmp_path, 14)
    assert len(removed) == 6
    assert len(list(tmp_path.glob("*.dump"))) == 14 and len(list(tmp_path.glob("*.json"))) == 14
    assert (tmp_path / "smarthive-20261020-030000.dump").exists()


@pytest.mark.skipif(
    shutil.which("pg_dump") is None and not list(Path("/usr/lib/postgresql").glob("*/bin/pg_dump")),
    reason="PostgreSQL client tools are not installed",
)
async def test_a_backup_restores_into_a_scratch_database(
    engine: AsyncEngine, db_url: str, tmp_path: Path
) -> None:
    await setup_hive(engine)
    dump = await maintenance.backup(db_url, tmp_path, keep=2)
    assert dump.stat().st_size > 0 and json.loads(dump.with_suffix(".json").read_text())["hives"] == 1
    result = await maintenance.restore_check(db_url, dump)
    assert result["hives"] == (1, 1) and result["users"][1] >= 1

    dump.with_suffix(".json").write_text(
        json.dumps({**json.loads(dump.with_suffix(".json").read_text()), "hives": 5})
    )
    with pytest.raises(RuntimeError, match="missing rows"):
        await maintenance.restore_check(db_url, dump)
