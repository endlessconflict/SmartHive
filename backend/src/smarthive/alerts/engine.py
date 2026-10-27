"""One pass over every enabled rule, and the worker loop that runs it on NOTIFY and on a timer."""

import asyncio
import logging
import time
from datetime import UTC, date, datetime
from pathlib import Path

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from smarthive import maintenance, weather
from smarthive.alerts import delivery, store
from smarthive.alerts.rules import RULES
from smarthive.api.deps import Db
from smarthive.config import Settings
from smarthive.ingest.handler import CHANNEL

log = logging.getLogger("smarthive.alerts")


async def evaluate_all(engine: AsyncEngine, now: datetime | None = None) -> int:
    """Run each enabled rule in its own transaction, so one broken rule does not stop the others."""
    now = now or datetime.now(UTC)
    opened = 0
    async with engine.connect() as c:
        rules = (await c.execute(text("SELECT id, severity, params FROM alert_rules WHERE enabled"))).all()
    for row in rules:
        rule = RULES.get(row.id)
        if rule is None:
            continue
        db = Db(engine)
        try:
            findings = await rule.evaluate(db, row.params, now)
            for f in findings:
                if await store.raise_alert(db, row.severity, f, now, once=rule.once):
                    opened += 1
            if rule.auto_resolve:
                await store.resolve_stale(db, rule.id, {f.dedup_key for f in findings}, now)
        except Exception:
            await db.finish(commit=False)
            log.exception("rule_failed", extra={"fields": {"rule": rule.id}})
        else:
            await db.finish(commit=True)
    return opened


async def _nightly(engine: AsyncEngine, settings: Settings) -> None:
    try:
        done = await maintenance.purge(engine, Path(settings.image_dir))
        log.info("purged", extra={"fields": done})
        if settings.backup_dir:
            dump = await maintenance.backup(settings.db_url, Path(settings.backup_dir), settings.backup_keep)
            log.info("backup_written", extra={"fields": {"file": dump.name}})
    except Exception:
        log.exception("nightly_failed")


async def run(settings: Settings, stop: asyncio.Event) -> None:
    """Evaluate when the ingestor announces a message, and at least every `alert_interval_s`."""
    engine = create_async_engine(settings.engine_url, pool_pre_ping=True)
    wake = asyncio.Event()
    listener = await asyncpg.connect(settings.db_url.replace("+asyncpg", ""))
    await listener.add_listener(CHANNEL, lambda *_: wake.set())
    last_weather = float("-inf")
    last_maintenance: date | None = None
    try:
        while not stop.is_set():
            if time.monotonic() - last_weather >= settings.weather_interval_s:
                last_weather = time.monotonic()
                try:
                    log.info("weather_stored", extra={"fields": {"rows": await weather.refresh_all(engine)}})
                except Exception:
                    log.exception("weather_failed")
            today = datetime.now(UTC)
            if today.hour >= settings.maintenance_hour_utc and last_maintenance != today.date():
                last_maintenance = today.date()
                await _nightly(engine, settings)
            try:
                opened = await evaluate_all(engine)
                log.info("alerts_evaluated", extra={"fields": {"opened": opened}})
                await delivery.deliver_pending(engine, settings)
            except Exception:
                log.exception("evaluation_failed")
            wake.clear()
            waiters = [asyncio.create_task(stop.wait()), asyncio.create_task(wake.wait())]
            await asyncio.wait(
                waiters, timeout=settings.alert_interval_s, return_when=asyncio.FIRST_COMPLETED
            )
            for t in waiters:
                t.cancel()
            await asyncio.sleep(0.5)  # a burst of messages becomes one evaluation
    finally:
        await listener.close()
        await engine.dispose()
