"""The interface for ML jobs (anomaly detection, yield prediction): read features, write results.

A job is a separate process that imports these functions with its own database engine. Everything it
writes carries the model name, so a result can always be traced to the model that made it. The API in
`api/routes/management.py` is the read side for the dashboard.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.alerts.rules import MASK_MARGIN


@dataclass(frozen=True)
class Feature:
    ts: datetime  # start of the bucket
    quantity: str
    mean: float
    min: float
    max: float
    n: int


async def read_features(
    engine: AsyncEngine,
    hive_id: UUID,
    start: datetime,
    end: datetime,
    bucket: timedelta = timedelta(minutes=15),
) -> list[Feature]:
    """Bucketed readings of quality `ok`, oldest first.

    Readings taken during a logged management event, or in the margin after it, are left out: an
    inspection must not look like an anomaly.
    """
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT time_bucket(CAST(:b AS interval), ts) AS ts, quantity, avg(value) AS mean, "
                    "min(value) AS min, max(value) AS max, count(*) AS n FROM readings "
                    "WHERE hive_id = :h AND quality = 'ok' AND value IS NOT NULL AND ts >= :s AND ts < :e "
                    "AND NOT EXISTS (SELECT 1 FROM management_events m WHERE m.hive_id = readings.hive_id "
                    "AND readings.ts >= m.started_at "
                    f"AND readings.ts < coalesce(m.ended_at, m.started_at) + interval '{MASK_MARGIN}') "
                    "GROUP BY 1, 2 ORDER BY 1, 2"
                ),
                {"b": bucket, "h": hive_id, "s": start, "e": end},
            )
        ).all()
    return [Feature(**r._mapping) for r in rows]


async def write_anomaly(
    engine: AsyncEngine,
    hive_id: UUID,
    start: datetime,
    end: datetime,
    score: float,
    model: str,
    kind: str | None = None,
) -> UUID:
    """Store one anomaly window. `kind` None means the model found something it cannot name."""
    if not model:
        raise ValueError("model is required")
    if start >= end:
        raise ValueError("start must be before end")
    anomaly_id = uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO anomalies (id, hive_id, period, score, kind, model) "
                "VALUES (:id, :h, tstzrange(:s, :e), :score, :kind, :model)"
            ),
            {
                "id": anomaly_id,
                "h": hive_id,
                "s": start,
                "e": end,
                "score": score,
                "kind": kind,
                "model": model,
            },
        )
    return anomaly_id


async def write_prediction(
    engine: AsyncEngine,
    hive_id: UUID,
    target: str,
    horizon: timedelta,
    p10: float,
    p50: float,
    p90: float,
    model: str,
    made_at: datetime | None = None,
) -> None:
    """Store a range forecast, for example target "yield_7d_kg" with horizon 7 days."""
    if not model:
        raise ValueError("model is required")
    if not p10 <= p50 <= p90:
        raise ValueError("expected p10 <= p50 <= p90")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO predictions (hive_id, made_at, target, horizon, p10, p50, p90, model) "
                "VALUES (:h, :at, :t, :hz, :p10, :p50, :p90, :model)"
            ),
            {
                "h": hive_id,
                "at": made_at or datetime.now(UTC),
                "t": target,
                "hz": horizon,
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "model": model,
            },
        )
