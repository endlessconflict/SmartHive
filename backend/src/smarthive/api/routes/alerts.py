import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from smarthive.alerts import store
from smarthive.api.deps import Admin, Conn, CurrentUser
from smarthive.api.errors import Problem
from smarthive.api.pagination import Cursor, Limit, decode_cursor, encode_cursor

router = APIRouter(prefix="/api/v1", tags=["alerts"])

_COLUMNS = (
    "a.id, a.hive_id, a.node_id, a.rule_id, a.severity, a.state, a.title, a.details, a.opened_at, "
    "a.last_seen_at, a.acknowledged_at, a.acknowledged_by, a.resolved_at, a.resolved_by, a.resolution_note"
)
# Beekeepers see alerts of their own hives; alerts with no hive are for administrators.
_VISIBLE = "(:admin OR ap.owner_id = :me)"
_FROM = "alerts a LEFT JOIN hives h ON h.id = a.hive_id LEFT JOIN apiaries ap ON ap.id = h.apiary_id"


class Alert(BaseModel):
    id: UUID
    hive_id: UUID | None
    node_id: str | None
    rule_id: str
    severity: str
    state: str
    title: str
    details: dict[str, Any]
    opened_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: UUID | None
    resolved_at: datetime | None
    resolved_by: UUID | None
    resolution_note: str | None


class AlertEvent(BaseModel):
    at: datetime
    kind: str
    actor: UUID | None
    data: dict[str, Any]


class AlertDetail(Alert):
    events: list[AlertEvent]


class AlertPage(BaseModel):
    items: list[Alert]
    next_cursor: str | None


class Resolution(BaseModel):
    note: str | None = Field(None, max_length=2000)


class AlertRule(BaseModel):
    id: str
    enabled: bool
    severity: Literal["info", "warning", "critical"]
    params: dict[str, Any]


class AlertRulePatch(BaseModel):
    enabled: bool | None = None
    severity: Literal["info", "warning", "critical"] | None = None
    params: dict[str, float | int | str] | None = None


@router.get("/alerts", response_model=AlertPage, summary="Alerts the caller may see, newest first")
async def list_alerts(
    conn: Conn,
    user: CurrentUser,
    state: Literal["open", "acknowledged", "resolved"] | None = None,
    severity: Literal["info", "warning", "critical"] | None = None,
    hive_id: UUID | None = None,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> AlertPage:
    after = decode_cursor(cursor)
    try:
        after_ts, after_id = (
            (None, None) if after is None else (datetime.fromisoformat(after[:-37]), UUID(after[-36:]))
        )
    except ValueError:
        raise Problem(400, "Invalid cursor") from None
    rows = (
        await conn.execute(
            text(
                f"SELECT {_COLUMNS} FROM {_FROM} WHERE {_VISIBLE} "
                "AND (CAST(:state AS text) IS NULL OR a.state = :state) "
                "AND (CAST(:sev AS text) IS NULL OR a.severity = :sev) "
                "AND (CAST(:hive AS uuid) IS NULL OR a.hive_id = :hive) "
                "AND (CAST(:ts AS timestamptz) IS NULL OR (a.opened_at, a.id) < (CAST(:ts AS timestamptz), CAST(:aid AS uuid))) "
                "ORDER BY a.opened_at DESC, a.id DESC LIMIT :n"
            ),
            {
                "admin": user.role == "admin",
                "me": user.id,
                "state": state,
                "sev": severity,
                "hive": hive_id,
                "ts": after_ts,
                "aid": after_id,
                "n": limit + 1,
            },
        )
    ).all()
    page = rows[:limit]
    last = page[-1] if page else None
    return AlertPage(
        items=[Alert(**r._mapping) for r in page],
        next_cursor=encode_cursor(f"{last.opened_at.isoformat()}|{last.id}")
        if last and len(rows) > limit
        else None,
    )


async def _visible_alert(conn: Conn, user: CurrentUser, alert_id: UUID) -> Alert:
    row = (
        await conn.execute(
            text(f"SELECT {_COLUMNS} FROM {_FROM} WHERE a.id = :id AND {_VISIBLE}"),
            {"id": alert_id, "admin": user.role == "admin", "me": user.id},
        )
    ).first()
    if row is None:
        raise Problem(404, "Alert not found")
    return Alert(**row._mapping)


@router.get("/alerts/{alert_id}", response_model=AlertDetail, summary="An alert with its event log")
async def get_alert(alert_id: UUID, conn: Conn, user: CurrentUser) -> AlertDetail:
    alert = await _visible_alert(conn, user, alert_id)
    events = (
        await conn.execute(
            text("SELECT at, kind, actor, data FROM alert_events WHERE alert_id = :id ORDER BY id"),
            {"id": alert_id},
        )
    ).all()
    return AlertDetail(**alert.model_dump(), events=[AlertEvent(**e._mapping) for e in events])


async def _move(conn: Conn, user: CurrentUser, alert_id: UUID, to: str, note: str | None) -> Alert:
    await _visible_alert(conn, user, alert_id)
    if not await store.transition(conn, alert_id, to, user.id, note, datetime.now(UTC)):
        raise Problem(409, f"Alert cannot move to {to} from its current state")
    return await _visible_alert(conn, user, alert_id)


@router.post("/alerts/{alert_id}/acknowledge", response_model=Alert, summary="Mark as seen")
async def acknowledge(alert_id: UUID, conn: Conn, user: CurrentUser) -> Alert:
    return await _move(conn, user, alert_id, "acknowledged", None)


@router.post("/alerts/{alert_id}/resolve", response_model=Alert, summary="Mark as handled")
async def resolve(alert_id: UUID, body: Resolution, conn: Conn, user: CurrentUser) -> Alert:
    return await _move(conn, user, alert_id, "resolved", body.note)


@router.get("/alert-rules", response_model=list[AlertRule], summary="Predefined rules and thresholds")
async def list_rules(conn: Conn, _: CurrentUser) -> list[AlertRule]:
    rows = (
        await conn.execute(text("SELECT id, enabled, severity, params FROM alert_rules ORDER BY id"))
    ).all()
    return [AlertRule(**r._mapping) for r in rows]


@router.patch("/alert-rules/{rule_id}", response_model=AlertRule, summary="Adjust a rule (administrator)")
async def patch_rule(rule_id: str, body: AlertRulePatch, conn: Conn, _: Admin) -> AlertRule:
    row = (
        await conn.execute(
            text("SELECT id, enabled, severity, params FROM alert_rules WHERE id = :id"), {"id": rule_id}
        )
    ).first()
    if row is None:
        raise Problem(404, "Rule not found")
    changes = body.model_dump(exclude_unset=True)
    if (
        changes.get("enabled", False) is None
        or changes.get("severity", "info") is None
        or changes.get("params", {}) is None
    ):
        raise Problem(422, "enabled, severity and params cannot be null")
    params = row.params
    if "params" in changes:
        unknown = set(changes["params"]) - set(params)
        if unknown:  # new keys would be ignored by the rule, so they are a typo
            raise Problem(422, "Unknown parameter", ", ".join(sorted(unknown)))
        for k, v in changes["params"].items():
            if type(v) is not type(params[k]) and not (
                isinstance(v, int | float) and isinstance(params[k], int | float)
            ):
                raise Problem(422, f"Parameter {k} must be {type(params[k]).__name__}")
        params = {**params, **changes["params"]}
    updated = (
        await conn.execute(
            text(
                "UPDATE alert_rules SET enabled = :en, severity = :sev, params = CAST(:p AS jsonb) "
                "WHERE id = :id RETURNING id, enabled, severity, params"
            ),
            {
                "id": rule_id,
                "en": changes.get("enabled", row.enabled),
                "sev": changes.get("severity", row.severity),
                "p": json.dumps(params),
            },
        )
    ).one()
    return AlertRule(**updated._mapping)
