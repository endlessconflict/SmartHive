from fastapi import APIRouter, Request
from sqlalchemy import text

from smarthive.api.errors import Problem

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness: the process is up")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness: the database answers")
async def readyz(request: Request) -> dict[str, str]:
    # not the per-request transaction dependency: a database that is down must give a 503, not a 500
    try:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        raise Problem(503, "Database unavailable") from None
    return {"status": "ready"}
