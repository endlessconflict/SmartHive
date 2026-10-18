from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from smarthive.api.deps import ApiaryId, Conn, HiveId
from smarthive.api.errors import Problem
from smarthive.api.pagination import Cursor, Limit, decode_uuid_cursor, encode_cursor

router = APIRouter(tags=["hives"])

_COLUMNS = "id, apiary_id, name, hive_type, boxes, installed_on, notes, archived"


class Hive(BaseModel):
    id: UUID
    apiary_id: UUID
    name: str
    hive_type: str | None
    boxes: int | None
    installed_on: date | None
    notes: str | None
    archived: bool


class HivePage(BaseModel):
    items: list[Hive]
    next_cursor: str | None


class HiveIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    hive_type: str | None = Field(None, max_length=64)
    boxes: int | None = Field(None, ge=1, le=20)
    installed_on: date | None = None
    notes: str | None = Field(None, max_length=4000)


class HivePatch(BaseModel):
    """Only the fields present in the body change; null clears a nullable one."""

    name: str | None = Field(None, min_length=1, max_length=200)
    hive_type: str | None = Field(None, max_length=64)
    boxes: int | None = Field(None, ge=1, le=20)
    installed_on: date | None = None
    notes: str | None = Field(None, max_length=4000)
    archived: bool | None = None


@router.get("/api/v1/apiaries/{apiary_id}/hives", response_model=HivePage, summary="Hives of an apiary")
async def list_hives(
    apiary_id: ApiaryId, conn: Conn, include_archived: bool = False, limit: Limit = 50, cursor: Cursor = None
) -> HivePage:
    after = decode_uuid_cursor(cursor)
    rows = (
        await conn.execute(
            text(
                f"SELECT {_COLUMNS} FROM hives WHERE apiary_id = :a AND (:arch OR NOT archived) "
                "AND (CAST(:after AS uuid) IS NULL OR id > CAST(:after AS uuid)) ORDER BY id LIMIT :n"
            ),
            {"a": apiary_id, "arch": include_archived, "after": after, "n": limit + 1},
        )
    ).all()
    page = rows[:limit]
    return HivePage(
        items=[Hive(**r._mapping) for r in page],
        next_cursor=encode_cursor(str(page[-1].id)) if len(rows) > limit else None,
    )


@router.post("/api/v1/apiaries/{apiary_id}/hives", response_model=Hive, status_code=201, summary="Add a hive")
async def create_hive(apiary_id: ApiaryId, body: HiveIn, conn: Conn) -> Hive:
    row = (
        await conn.execute(
            text(
                "INSERT INTO hives (id, apiary_id, name, hive_type, boxes, installed_on, notes) "
                f"VALUES (:id, :a, :name, :hive_type, :boxes, :installed_on, :notes) RETURNING {_COLUMNS}"
            ),
            {"id": uuid4(), "a": apiary_id, **body.model_dump()},
        )
    ).one()
    return Hive(**row._mapping)


@router.get("/api/v1/hives/{hive_id}", response_model=Hive, summary="One hive")
async def get_hive(hive_id: HiveId, conn: Conn) -> Hive:
    row = (await conn.execute(text(f"SELECT {_COLUMNS} FROM hives WHERE id = :id"), {"id": hive_id})).one()
    return Hive(**row._mapping)


@router.patch("/api/v1/hives/{hive_id}", response_model=Hive, summary="Edit or archive a hive")
async def patch_hive(hive_id: HiveId, body: HivePatch, conn: Conn) -> Hive:
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name", "x") is None or changes.get("archived", False) is None:
        raise Problem(422, "name and archived cannot be null")
    if not changes:
        return await get_hive(hive_id, conn)
    # column names come from the model's own field names, never from the request
    sets = ", ".join(f"{k} = :{k}" for k in changes)
    row = (
        await conn.execute(
            text(f"UPDATE hives SET {sets} WHERE id = :id RETURNING {_COLUMNS}"), {"id": hive_id, **changes}
        )
    ).one()
    return Hive(**row._mapping)
