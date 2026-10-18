"""Image upload from the nodes (device token) and the gallery for the dashboard (user token)."""

import asyncio
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError
from sqlalchemy import text

from smarthive.api.deps import Config, Conn, CurrentUser, HiveId
from smarthive.api.errors import Problem
from smarthive.api.pagination import Cursor, Limit, decode_cursor, encode_cursor
from smarthive.api.security import hash_refresh_token
from smarthive.contracts.image import ImageMeta

router = APIRouter(tags=["images"])
_bearer = HTTPBearer(auto_error=False)
_JPEG = b"\xff\xd8\xff"
# data-model retention: threat and varroa pictures are evidence, the rest is routine
_KEEP = {"threat": timedelta(days=365), "varroa": timedelta(days=365)}
_KEEP_DEFAULT = timedelta(days=30)
_COLUMNS = "id, node_id, hive_id, captured_at, clock_synced, reason, sha256, bytes, width, height, objects"


class Image(BaseModel):
    id: UUID
    node_id: str
    hive_id: UUID | None
    captured_at: datetime
    clock_synced: bool
    reason: str
    sha256: str
    bytes: int
    width: int | None
    height: int | None
    objects: list[dict[str, Any]]


class ImagePage(BaseModel):
    items: list[Image]
    next_cursor: str | None


async def device_node(
    conn: Conn, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> str:
    """The node a device token belongs to."""
    if credentials is None:
        raise Problem(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    row = (
        await conn.execute(
            text("SELECT id FROM nodes WHERE device_token_hash = :h"),
            {"h": hash_refresh_token(credentials.credentials)},
        )
    ).first()
    if row is None:
        raise Problem(401, "Invalid device token", headers={"WWW-Authenticate": "Bearer"})
    return str(row.id)


def _store(root: Path, digest: str, data: bytes) -> str:
    """Write once under a content-addressed path; returns the path relative to the image volume."""
    rel = f"{digest[:2]}/{digest[2:4]}/{digest}.jpg"
    target = root / rel
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    return rel


@router.post("/device/v1/images", status_code=201, summary="Upload an image (device token)")
async def upload_image(
    node: Annotated[str, Depends(device_node)],
    settings: Config,
    conn: Conn,
    meta: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> JSONResponse:
    try:
        m = ImageMeta.model_validate_json(meta)
    except ValidationError as e:
        raise Problem(
            422,
            "Invalid meta",
            "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:5]),
        ) from None
    if m.node_id != node:
        raise Problem(403, "The token belongs to another node")
    if file.content_type != "image/jpeg":
        raise Problem(415, "Only image/jpeg is accepted")
    data = await file.read(settings.image_max_bytes + 1)
    if len(data) > settings.image_max_bytes:
        raise Problem(413, "Image too large")
    if not data.startswith(_JPEG):
        raise Problem(415, "The file is not a JPEG")
    if hashlib.sha256(data).hexdigest() != m.sha256:
        raise Problem(422, "sha256 does not match the file")

    known = (await conn.execute(text("SELECT sha256 FROM images WHERE id = :i"), {"i": m.image_id})).first()
    if known is not None:
        if known.sha256 != m.sha256:
            raise Problem(409, "image_id exists with a different hash")
        return JSONResponse({"image_id": str(m.image_id)}, status_code=200)

    rel = await asyncio.to_thread(_store, Path(settings.image_dir), m.sha256, data)
    await conn.execute(
        text(
            "INSERT INTO images (id, node_id, hive_id, captured_at, clock_synced, reason, path, sha256, "
            "bytes, "
            "width, height, objects, expires_at) VALUES (:id, :n, "
            "(SELECT hive_id FROM node_assignments WHERE node_id = :n "
            "AND valid @> CAST(:ts AS timestamptz) LIMIT 1), "
            "CAST(:ts AS timestamptz), :sync, :reason, :path, :sha, :bytes, :w, :h, "
            "CAST(:objects AS jsonb), :exp)"
        ),
        {
            "id": m.image_id,
            "n": node,
            "ts": m.captured_at,
            "sync": m.clock_synced,
            "reason": m.reason,
            "path": rel,
            "sha": m.sha256,
            "bytes": len(data),
            "w": m.width,
            "h": m.height,
            "objects": "[" + ",".join(o.model_dump_json() for o in m.objects) + "]",
            "exp": m.captured_at + _KEEP.get(m.reason, _KEEP_DEFAULT),
        },
    )
    return JSONResponse({"image_id": str(m.image_id)}, status_code=201)


async def _page(
    conn: Conn,
    hive_id: UUID,
    reason: str | None,
    start: datetime | None,
    end: datetime | None,
    limit: int,
    cursor: str | None,
) -> ImagePage:
    after_ts, after_id = None, None
    if (raw := decode_cursor(cursor)) is not None:
        try:
            ts, i = raw.split("|")
            after_ts, after_id = datetime.fromisoformat(ts), UUID(i)
        except ValueError:
            raise Problem(400, "Invalid cursor") from None
    rows = (
        await conn.execute(
            text(
                f"SELECT {_COLUMNS} FROM images WHERE hive_id = :h "
                "AND (CAST(:reason AS text) IS NULL OR reason = :reason) "
                "AND (CAST(:start AS timestamptz) IS NULL OR captured_at >= :start) "
                "AND (CAST(:end AS timestamptz) IS NULL OR captured_at < :end) "
                "AND (CAST(:ats AS timestamptz) IS NULL "
                "OR (captured_at, id) < (CAST(:ats AS timestamptz), CAST(:aid AS uuid))) "
                "ORDER BY captured_at DESC, id DESC LIMIT :n"
            ),
            {
                "h": hive_id,
                "reason": reason,
                "start": start,
                "end": end,
                "ats": after_ts,
                "aid": after_id,
                "n": limit + 1,
            },
        )
    ).all()
    page = rows[:limit]
    return ImagePage(
        items=[Image(**r._mapping) for r in page],
        next_cursor=encode_cursor(f"{page[-1].captured_at.isoformat()}|{page[-1].id}")
        if len(rows) > limit
        else None,
    )


@router.get("/api/v1/hives/{hive_id}/images", response_model=ImagePage, summary="Image gallery of a hive")
async def hive_images(
    hive_id: HiveId,
    conn: Conn,
    reason: str | None = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> ImagePage:
    return await _page(conn, hive_id, reason, start, end, limit, cursor)


@router.get("/api/v1/hives/{hive_id}/images/latest", response_model=Image, summary="Most recent image")
async def latest_image(hive_id: HiveId, conn: Conn) -> Image:
    page = await _page(conn, hive_id, None, None, None, 1, None)
    if not page.items:
        raise Problem(404, "No images yet")
    return page.items[0]


async def _visible_image(conn: Conn, user: CurrentUser, image_id: UUID) -> Any:
    """404 for an image of someone else's hive, and for an unassigned one unless the caller is an admin."""
    row = (
        await conn.execute(
            text(
                "SELECT i.*, a.owner_id FROM images i LEFT JOIN hives h ON h.id = i.hive_id "
                "LEFT JOIN apiaries a ON a.id = h.apiary_id WHERE i.id = :i"
            ),
            {"i": image_id},
        )
    ).first()
    if row is None or not (user.role == "admin" or row.owner_id == user.id):
        raise Problem(404, "Image not found")
    return row


@router.get("/api/v1/images/{image_id}", response_model=Image, summary="Image metadata")
async def get_image(image_id: UUID, conn: Conn, user: CurrentUser) -> Image:
    return Image(**(await _visible_image(conn, user, image_id))._mapping)


@router.get("/api/v1/images/{image_id}/file", summary="The JPEG")
async def image_file(image_id: UUID, conn: Conn, user: CurrentUser, settings: Config) -> FileResponse:
    row = await _visible_image(conn, user, image_id)
    path = Path(settings.image_dir) / row.path
    if not path.is_file():
        raise Problem(404, "The file is gone")  # purged or the volume was not restored
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
