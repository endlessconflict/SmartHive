from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from smarthive.api.deps import ApiaryId, Conn, CurrentUser
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


class ApiaryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    timezone: str = Field("America/Panama", max_length=64)


_COLUMNS = "id, owner_id, name, lat, lon, timezone"


@router.post("", response_model=Apiary, status_code=201, summary="Create an apiary owned by the caller")
async def create_apiary(body: ApiaryIn, conn: Conn, user: CurrentUser) -> Apiary:
    row = (
        await conn.execute(
            text(
                "INSERT INTO apiaries (id, owner_id, name, lat, lon, timezone) "
                f"VALUES (:id, :me, :name, :lat, :lon, :tz) RETURNING {_COLUMNS}"
            ),
            {
                "id": uuid4(),
                "me": user.id,
                "name": body.name,
                "lat": body.lat,
                "lon": body.lon,
                "tz": body.timezone,
            },
        )
    ).one()
    return Apiary(**row._mapping)


@router.get("/{apiary_id}", response_model=Apiary, summary="One apiary")
async def get_apiary(apiary_id: ApiaryId, conn: Conn) -> Apiary:
    row = (
        await conn.execute(text(f"SELECT {_COLUMNS} FROM apiaries WHERE id = :id"), {"id": apiary_id})
    ).one()
    return Apiary(**row._mapping)
