from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from smarthive.api.deps import Conn, CurrentUser
from smarthive.api.errors import Problem
from smarthive.api.pagination import Cursor, Limit, decode_cursor, encode_cursor

router = APIRouter(prefix="/api/v1", tags=["me"])


class Me(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    notify_email: bool
    ntfy_topic: str | None


class MePatch(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=200)
    notify_email: bool | None = None
    ntfy_topic: str | None = Field(None, max_length=200, description="Empty string turns ntfy off")


class Notification(BaseModel):
    id: int
    alert_id: UUID
    hive_id: UUID | None
    severity: str
    title: str
    alert_state: str
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[Notification]
    next_cursor: str | None
    unread: int  # all of the caller's unread, not only this page


def _me(user: CurrentUser) -> Me:
    return Me(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        notify_email=user.notify_email,
        ntfy_topic=user.ntfy_topic,
    )


@router.get("/me", response_model=Me, summary="The signed-in user")
async def me(user: CurrentUser) -> Me:
    return _me(user)


@router.patch("/me", response_model=Me, summary="Change your name and notification channels")
async def patch_me(body: MePatch, conn: Conn, user: CurrentUser) -> Me:
    changes = body.model_dump(exclude_unset=True)
    if changes.get("ntfy_topic") == "":
        changes["ntfy_topic"] = None
    for field in ("display_name", "notify_email"):
        if field in changes and changes[field] is None:
            raise Problem(422, f"{field} cannot be null")
    if changes:
        # column names come from the model's own fields, never from the request
        sets = ", ".join(f"{k} = :{k}" for k in changes)
        await conn.execute(text(f"UPDATE users SET {sets} WHERE id = :id"), {**changes, "id": user.id})
    row = (
        await conn.execute(
            text("SELECT display_name, notify_email, ntfy_topic FROM users WHERE id = :id"), {"id": user.id}
        )
    ).one()
    return _me(user).model_copy(update=dict(row._mapping))


@router.get(
    "/me/notifications",
    response_model=NotificationPage,
    summary="Your in-app notifications (the inbox), newest first",
)
async def list_notifications(
    conn: Conn, user: CurrentUser, unread: bool = False, limit: Limit = 50, cursor: Cursor = None
) -> NotificationPage:
    value = decode_cursor(cursor)
    try:
        after = None if value is None else int(value)
    except ValueError:
        raise Problem(400, "Invalid cursor") from None
    rows = (
        await conn.execute(
            text(
                "SELECT n.id, n.alert_id, a.hive_id, a.severity, a.title, a.state AS alert_state, "
                "a.opened_at AS created_at, n.read_at FROM notifications n JOIN alerts a ON a.id = n.alert_id "
                "WHERE n.user_id = :me AND n.channel = 'app' "
                "AND (NOT :unread OR n.read_at IS NULL) AND (CAST(:after AS bigint) IS NULL OR n.id < :after) "
                "ORDER BY n.id DESC LIMIT :n"
            ),
            {"me": user.id, "unread": unread, "after": after, "n": limit + 1},
        )
    ).all()
    count = (
        await conn.execute(
            text(
                "SELECT count(*) FROM notifications WHERE user_id = :me AND channel = 'app' AND read_at IS NULL"
            ),
            {"me": user.id},
        )
    ).scalar_one()
    page = rows[:limit]
    return NotificationPage(
        items=[Notification(**r._mapping) for r in page],
        next_cursor=encode_cursor(str(page[-1].id)) if page and len(rows) > limit else None,
        unread=count,
    )


@router.post("/me/notifications/read-all", status_code=204, summary="Mark every notification as read")
async def read_all(conn: Conn, user: CurrentUser) -> None:
    await conn.execute(
        text(
            "UPDATE notifications SET read_at = now() "
            "WHERE user_id = :me AND channel = 'app' AND read_at IS NULL"
        ),
        {"me": user.id},
    )


@router.post("/me/notifications/{notification_id}/read", status_code=204, summary="Mark one as read")
async def read_one(notification_id: int, conn: Conn, user: CurrentUser) -> None:
    done = await conn.execute(
        text(
            "UPDATE notifications SET read_at = coalesce(read_at, now()) "
            "WHERE id = :id AND user_id = :me AND channel = 'app'"
        ),
        {"id": notification_id, "me": user.id},
    )
    if done.rowcount == 0:
        raise Problem(404, "Notification not found")
