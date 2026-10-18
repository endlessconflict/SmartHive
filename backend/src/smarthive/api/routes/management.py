"""The beekeeper's log, and the anomaly windows and predictions that ML jobs write (see smarthive.jobs)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import text

from smarthive.api.deps import Conn, CurrentUser, HiveId
from smarthive.api.errors import Problem

router = APIRouter(tags=["management"])

EventType = Literal["inspection", "super_added", "super_removed", "harvest", "feeding", "treatment"]
Limit = Annotated[int, Query(ge=1, le=200)]


class ManagementEventIn(BaseModel):
    type: EventType
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    data: dict[str, Any] = Field(default_factory=dict, description='For example {"harvest_kg": 8.5}')


class ManagementEvent(ManagementEventIn):
    id: UUID
    hive_id: UUID
    created_by: UUID | None


class Anomaly(BaseModel):
    id: UUID
    hive_id: UUID
    start: datetime
    end: datetime
    score: float
    kind: str | None  # None: a pattern the model could not name
    model: str


class Prediction(BaseModel):
    hive_id: UUID
    target: str
    made_at: datetime
    horizon_s: float
    p10: float | None
    p50: float | None
    p90: float | None
    model: str


def _window(start: datetime | None, end: datetime | None, days: int) -> tuple[datetime, datetime]:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=days)
    if start.tzinfo is None or end.tzinfo is None:
        raise Problem(422, "start and end need a timezone offset")
    if start >= end:
        raise Problem(422, "start must be before end")
    return start, end


@router.post(
    "/api/v1/hives/{hive_id}/management-events",
    response_model=ManagementEvent,
    status_code=201,
    summary="Log an inspection, harvest, feeding or treatment",
)
async def log_event(
    hive_id: HiveId, body: ManagementEventIn, conn: Conn, user: CurrentUser
) -> ManagementEvent:
    if body.ended_at is not None and body.ended_at < body.started_at:
        raise Problem(422, "ended_at must not be before started_at")
    event_id = uuid4()
    await conn.execute(
        text(
            "INSERT INTO management_events (id, hive_id, type, started_at, ended_at, data, created_by) "
            "VALUES (:id, :h, :t, :s, :e, CAST(:d AS jsonb), :u)"
        ),
        {
            "id": event_id,
            "h": hive_id,
            "t": body.type,
            "s": body.started_at,
            "e": body.ended_at,
            "d": json.dumps(body.data),
            "u": user.id,
        },
    )
    return ManagementEvent(id=event_id, hive_id=hive_id, created_by=user.id, **body.model_dump())


@router.get(
    "/api/v1/hives/{hive_id}/management-events",
    response_model=list[ManagementEvent],
    summary="Logged events that overlap the range, newest first",
)
async def list_events(
    hive_id: HiveId,
    conn: Conn,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    limit: Limit = 50,
) -> list[ManagementEvent]:
    start, end = _window(start, end, 90)
    rows = (
        await conn.execute(
            text(
                "SELECT id, hive_id, type, started_at, ended_at, data, created_by FROM management_events "
                "WHERE hive_id = :h AND started_at < :e AND coalesce(ended_at, started_at) >= :s "
                "ORDER BY started_at DESC, id LIMIT :n"
            ),
            {"h": hive_id, "s": start, "e": end, "n": limit},
        )
    ).all()
    return [ManagementEvent(**r._mapping) for r in rows]


@router.get(
    "/api/v1/hives/{hive_id}/anomalies",
    response_model=list[Anomaly],
    summary="Anomaly windows that overlap the range, newest first",
)
async def list_anomalies(
    hive_id: HiveId,
    conn: Conn,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    limit: Limit = 100,
) -> list[Anomaly]:
    start, end = _window(start, end, 30)
    rows = (
        await conn.execute(
            text(
                'SELECT id, hive_id, lower(period) AS start, upper(period) AS "end", score, kind, model '
                "FROM anomalies WHERE hive_id = :h AND period && tstzrange(:s, :e) "
                "ORDER BY lower(period) DESC, id LIMIT :n"
            ),
            {"h": hive_id, "s": start, "e": end, "n": limit},
        )
    ).all()
    return [Anomaly(**r._mapping) for r in rows]


@router.get(
    "/api/v1/hives/{hive_id}/predictions",
    response_model=list[Prediction],
    summary="The latest prediction per target, as a p10 to p90 range",
)
async def latest_predictions(
    hive_id: HiveId, conn: Conn, target: Annotated[str | None, Query(max_length=64)] = None
) -> list[Prediction]:
    rows = (
        await conn.execute(
            text(
                "SELECT DISTINCT ON (target) hive_id, target, made_at, "
                "extract(epoch FROM horizon) AS horizon_s, "
                "p10, p50, p90, model FROM predictions "
                "WHERE hive_id = :h AND (CAST(:t AS text) IS NULL OR target = :t) "
                "ORDER BY target, made_at DESC"
            ),
            {"h": hive_id, "t": target},
        )
    ).all()
    return [Prediction(**r._mapping) for r in rows]
