from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import text

from smarthive.api.deps import Conn, HiveId
from smarthive.api.errors import Problem

router = APIRouter(tags=["readings"])

# A closed set, so the interval can go into time_bucket() as a literal without injection risk.
Bucket = Literal["raw", "1m", "5m", "15m", "1h", "1d"]
_INTERVAL = {"1m": "1 minute", "5m": "5 minutes", "15m": "15 minutes", "1h": "1 hour", "1d": "1 day"}
MAX_POINTS = 5000


class Point(BaseModel):
    ts: datetime
    value: float | None
    min: float | None = None
    max: float | None = None
    n: int = 1


class Series(BaseModel):
    hive_id: UUID
    quantity: str
    bucket: Bucket
    points: list[Point]
    truncated: bool


@router.get("/api/v1/hives/{hive_id}/readings", response_model=Series, summary="One quantity over time")
async def hive_readings(
    hive_id: HiveId,
    conn: Conn,
    quantity: Annotated[str, Query(min_length=1, max_length=64)],
    start: datetime | None = None,
    end: datetime | None = None,
    bucket: Bucket = "raw",
) -> Series:
    """Oldest first, last 24 h by default. Only quality `ok` counts; `truncated` flags a capped range."""
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=1)
    if start.tzinfo is None or end.tzinfo is None:
        raise Problem(422, "start and end need a timezone offset")
    if start >= end:
        raise Problem(422, "start must be before end")
    where = "WHERE hive_id = :h AND quantity = :q AND quality = 'ok' AND ts >= :s AND ts < :e"
    if bucket == "raw":
        sql = f"SELECT ts, value FROM readings {where} ORDER BY ts LIMIT :n"
    else:
        sql = (
            f"SELECT time_bucket('{_INTERVAL[bucket]}', ts) AS ts, avg(value) AS value, "
            f"min(value) AS min, max(value) AS max, count(*) AS n FROM readings {where} "
            "GROUP BY 1 ORDER BY 1 LIMIT :n"
        )
    rows = (
        await conn.execute(
            text(sql), {"h": hive_id, "q": quantity, "s": start, "e": end, "n": MAX_POINTS + 1}
        )
    ).all()
    return Series(
        hive_id=hive_id,
        quantity=quantity,
        bucket=bucket,
        points=[Point(**r._mapping) for r in rows[:MAX_POINTS]],
        truncated=len(rows) > MAX_POINTS,
    )
