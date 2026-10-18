"""Login, refresh and logout. The access token is a 15-minute JWT; the refresh token is opaque and lives
in an HttpOnly cookie. Only its hash is stored, it is rotated on every use, and a token used twice means
it leaked, so every session of that user is closed."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from smarthive.api.deps import Config, Conn, Db
from smarthive.api.errors import Problem, problem_response
from smarthive.api.security import (
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from smarthive.config import Settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
COOKIE = "refresh_token"


class LoginRequest(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=1024)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def _set_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=router.prefix,  # the browser sends it to the auth endpoints only
    )


def _clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        COOKIE, path=router.prefix, httponly=True, secure=settings.cookie_secure, samesite="strict"
    )


async def _issue(conn: Db, settings: Settings, user_id: UUID, role: str) -> tuple[JSONResponse, UUID]:
    token, digest = new_refresh_token()
    token_id = uuid4()
    await conn.execute(
        text("INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at) VALUES (:id, :u, :h, :exp)"),
        {
            "id": token_id,
            "u": user_id,
            "h": digest,
            "exp": datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        },
    )
    body = TokenResponse(
        access_token=create_access_token(settings.jwt_secret, user_id, role, settings.access_token_minutes),
        expires_in=settings.access_token_minutes * 60,
    )
    response = JSONResponse(body.model_dump())
    _set_cookie(response, settings, token)
    return response, token_id


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse, summary="Exchange email and password for tokens")
async def login(body: LoginRequest, request: Request, conn: Conn, settings: Config) -> Response:
    limiter = request.app.state.login_limiter
    client = _client(request)
    if limiter.blocked(client):
        raise Problem(
            429,
            "Too many failed logins",
            "Try again later.",
            headers={"Retry-After": str(limiter.retry_after(client))},
        )
    row = (
        await conn.execute(
            text("SELECT id, password_hash, role FROM users WHERE email = :email"), {"email": body.email}
        )
    ).first()
    # one answer for "no such user" and "wrong password", and the same amount of hashing work for both
    if not verify_password(body.password, row.password_hash if row else None) or row is None:
        limiter.fail(client)
        return problem_response(401, "Invalid email or password")
    limiter.reset(client)
    response, _ = await _issue(conn, settings, row.id, row.role)
    return response


@router.post("/refresh", response_model=TokenResponse, summary="Trade the refresh cookie for new tokens")
async def refresh(
    conn: Conn, settings: Config, refresh_token: Annotated[str | None, Cookie(alias=COOKIE)] = None
) -> Response:
    # Failures return a response instead of raising: raising rolls the transaction back, and the
    # revocation after a reused token has to be committed.
    def rejected() -> Response:
        response = problem_response(401, "Invalid or expired refresh token")
        _clear_cookie(response, settings)
        return response

    if not refresh_token:
        return rejected()
    row = (
        await conn.execute(
            text(
                "SELECT t.id, t.user_id, t.expires_at, t.revoked_at, u.role FROM refresh_tokens t "
                "JOIN users u ON u.id = t.user_id WHERE t.token_hash = :h FOR UPDATE OF t"
            ),
            {"h": hash_refresh_token(refresh_token)},
        )
    ).first()
    if row is None:
        return rejected()
    if row.revoked_at is not None:
        await conn.execute(
            text("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = :u AND revoked_at IS NULL"),
            {"u": row.user_id},
        )
        return rejected()
    if row.expires_at <= datetime.now(UTC):
        return rejected()
    response, new_id = await _issue(conn, settings, row.user_id, row.role)
    await conn.execute(
        text("UPDATE refresh_tokens SET revoked_at = now(), replaced_by = :n WHERE id = :id"),
        {"n": new_id, "id": row.id},
    )
    return response


@router.post("/logout", status_code=204, summary="Close this session")
async def logout(
    conn: Conn, settings: Config, refresh_token: Annotated[str | None, Cookie(alias=COOKIE)] = None
) -> Response:
    if refresh_token:
        await conn.execute(
            text("UPDATE refresh_tokens SET revoked_at = now() WHERE token_hash = :h AND revoked_at IS NULL"),
            {"h": hash_refresh_token(refresh_token)},
        )
    response = Response(status_code=204)
    _clear_cookie(response, settings)
    return response
