"""Downloads for researchers (REQ-09), and the stored site weather for chart overlays."""

import csv
import io
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import text

from smarthive.api.deps import Conn, HiveId
from smarthive.api.errors import Problem

router = APIRouter(tags=["exports"])

Format = Literal["csv", "jsonl"]
CHUNK_ROWS = 2000

# `nodes.is_simulated` decides: simulated rows only come out when the caller asks for them, and the header
# says which kind the file holds, so a file can never pass for the other kind.
_READINGS = (
    "SELECT r.ts, r.node_id, r.quantity, r.value, r.quality, r.clock_synced FROM readings r "
    "JOIN nodes n ON n.id = r.node_id WHERE r.hive_id = :h AND r.ts >= :s AND r.ts < :e "
    "AND (CAST(:q AS text) IS NULL OR r.quantity = :q) AND (:sim OR NOT n.is_simulated) "
    "ORDER BY r.ts, r.quantity"
)
_DETECTIONS = (
    "SELECT d.first_seen, d.last_seen, d.node_id, d.type, d.cls, d.max_conf, d.frames_positive, "
    "d.frames_window, d.episode_id, d.image_id FROM detection_events d JOIN nodes n ON n.id = d.node_id "
    "WHERE d.hive_id = :h AND d.first_seen >= :s AND d.first_seen < :e AND (:sim OR NOT n.is_simulated) "
    "ORDER BY d.first_seen, d.msg_id"
)
_SOURCES = (
    "SELECT DISTINCT {t}.node_id, n.is_simulated FROM {t} JOIN nodes n ON n.id = {t}.node_id "
    "WHERE {t}.hive_id = :h AND {t}.{c} >= :s AND {t}.{c} < :e AND (:sim OR NOT n.is_simulated) ORDER BY 1"
)


def _cell(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


async def _stream(
    request: Request, sql: str, params: dict[str, Any], fmt: Format, meta: dict[str, Any]
) -> AsyncIterator[str]:
    """Rows come from a server-side cursor, so a long range never sits in memory."""
    if fmt == "csv":
        yield "".join(f"# {k}: {v}\n" for k, v in meta.items())
    else:
        yield json.dumps({"meta": meta}) + "\n"
    async with request.app.state.engine.connect() as conn:
        result = await conn.stream(text(sql), params)
        header_done = False
        async for chunk in result.partitions(CHUNK_ROWS):
            out = io.StringIO()
            writer = csv.writer(out, lineterminator="\n")
            for row in chunk:
                values = {k: _cell(v) for k, v in row._mapping.items()}
                if fmt == "jsonl":
                    out.write(json.dumps(values, default=str) + "\n")
                    continue
                if not header_done:
                    writer.writerow(values)
                    header_done = True
                writer.writerow(values.values())
            yield out.getvalue()


async def _export(
    request: Request,
    conn: Conn,
    sql: str,
    column: str,
    table: str,
    hive_id: Any,
    start: datetime | None,
    end: datetime | None,
    simulated: bool,
    fmt: Format,
    extra: dict[str, Any],
    name: str,
) -> StreamingResponse:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=30)
    if start >= end:
        raise Problem(422, "start must be before end")
    params = {"h": hive_id, "s": start, "e": end, "sim": simulated, **extra}
    nodes = (
        await conn.execute(
            text(_SOURCES.format(t=table, c=column)), {k: params[k] for k in ("h", "s", "e", "sim")}
        )
    ).all()
    meta = {
        "hive_id": str(hive_id),
        "nodes": ",".join(n.node_id for n in nodes) or "none",
        "simulated": "yes"
        if nodes and all(n.is_simulated for n in nodes)
        else "mixed"
        if any(n.is_simulated for n in nodes)
        else "no",
        "from": start.isoformat(),
        "to": end.isoformat(),
        "generated": datetime.now(UTC).isoformat(),
    }
    media = "text/csv" if fmt == "csv" else "application/x-ndjson"
    return StreamingResponse(
        _stream(request, sql, params, fmt, meta),
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}-{str(hive_id)[:8]}.{fmt}"'},
    )


@router.get("/api/v1/exports/readings", summary="Readings as CSV or JSON Lines, with quality flags")
async def export_readings(
    request: Request,
    conn: Conn,
    hive_id: HiveId,
    quantity: Annotated[str | None, Query(max_length=64)] = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    include_simulated: bool = False,
    format: Format = "csv",
) -> StreamingResponse:
    return await _export(
        request, conn, _READINGS, "ts", "readings", hive_id, start, end, include_simulated, format,
        {"q": quantity}, "readings",
    )  # fmt: skip


@router.get("/api/v1/exports/detections", summary="Detection events as CSV or JSON Lines")
async def export_detections(
    request: Request,
    conn: Conn,
    hive_id: HiveId,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    include_simulated: bool = False,
    format: Format = "csv",
) -> StreamingResponse:
    return await _export(
        request, conn, _DETECTIONS, "first_seen", "detection_events", hive_id, start, end,
        include_simulated, format, {}, "detections",
    )  # fmt: skip


class WeatherPoint(BaseModel):
    ts: datetime
    temp_c: float | None
    rh_pct: float | None
    precip_mm: float | None
    wind_ms: float | None
    radiation_wm2: float | None


@router.get(
    "/api/v1/hives/{hive_id}/weather",
    response_model=list[WeatherPoint],
    summary="Stored hourly weather at the hive's apiary, for chart overlays",
)
async def hive_weather(
    hive_id: HiveId, conn: Conn, start: AwareDatetime | None = None, end: AwareDatetime | None = None
) -> list[WeatherPoint]:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=7)
    if start >= end:
        raise Problem(422, "start must be before end")
    rows = (
        await conn.execute(
            text(
                "SELECT w.ts, w.temp_c, w.rh_pct, w.precip_mm, w.wind_ms, w.radiation_wm2 FROM weather w "
                "JOIN hives h ON h.apiary_id = w.apiary_id WHERE h.id = :h AND w.ts >= :s AND w.ts < :e "
                "ORDER BY w.ts LIMIT 5000"
            ),
            {"h": hive_id, "s": start, "e": end},
        )
    ).all()
    return [WeatherPoint(**r._mapping) for r in rows]
