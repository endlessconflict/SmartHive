"""Errors as RFC 9457 problem details: {"type", "title", "status", "detail"}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("smarthive.api")
MEDIA_TYPE = "application/problem+json"


class Problem(Exception):
    """Raise this from a route to return a problem document."""

    def __init__(
        self, status: int, title: str, detail: str | None = None, headers: dict[str, str] | None = None
    ):
        super().__init__(title)
        self.status = status
        self.title = title
        self.detail = detail
        self.headers = headers or {}


def problem_response(
    status: int, title: str, detail: str | None = None, headers: dict[str, str] | None = None, **extra: Any
) -> JSONResponse:
    body: dict[str, Any] = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=MEDIA_TYPE, headers=headers)


def install(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def _problem(_: Request, e: Problem) -> JSONResponse:
        return problem_response(e.status, e.title, e.detail, e.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException) -> JSONResponse:
        return problem_response(e.status_code, str(e.detail), headers=dict(e.headers or {}))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError) -> JSONResponse:
        errors = [{"loc": ".".join(map(str, err["loc"])), "msg": err["msg"]} for err in e.errors()]
        return problem_response(422, "Request validation failed", errors=errors)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, e: Exception) -> JSONResponse:
        log.exception("unhandled_error", extra={"fields": {"path": request.url.path}})
        return problem_response(
            500, "Internal server error"
        )  # the cause stays in the log, not in the response
