from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from smarthive.api.deps import Conn, CurrentUser
from smarthive.api.pagination import Cursor, Limit, decode_uuid_cursor, encode_cursor

router = APIRouter(prefix="/api/v1/apiaries", tags=["apiaries"])


class Apiary(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    lat: float | None
    lon: float | None
    timezone: str


class ApiaryPage(BaseModel):
    items: list[Apiary]
    next_cursor: str | None


@router.get("", response_model=ApiaryPage, summary="Apiaries the caller may see")
async def list_apiaries(
    conn: Conn, user: CurrentUser, limit: Limit = 50, cursor: Cursor = None
) -> ApiaryPage:
    """A beekeeper sees the apiaries they own; an administrator sees all of them."""
    after = decode_uuid_cursor(cursor)
    rows = (
        await conn.execute(
            text(
                "SELECT id, owner_id, name, lat, lon, timezone FROM apiaries "
                "WHERE (:admin OR owner_id = :me) "
                "AND (CAST(:after AS uuid) IS NULL OR id > CAST(:after AS uuid)) "
                "ORDER BY id LIMIT :n"
            ),
            {"admin": user.role == "admin", "me": user.id, "after": after, "n": limit + 1},
        )
    ).all()
    page = rows[:limit]
    return ApiaryPage(
        items=[Apiary(**r._mapping) for r in page],
        next_cursor=encode_cursor(str(page[-1].id)) if len(rows) > limit else None,
    )
