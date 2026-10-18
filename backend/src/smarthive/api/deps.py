"""FastAPI dependencies: settings, one transaction per request, and who is calling."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.sql.elements import TextClause

from smarthive.api.errors import Problem
from smarthive.api.security import InvalidToken, decode_access_token
from smarthive.config import Settings

_bearer = HTTPBearer(auto_error=False)
_UNAUTHENTICATED = {"WWW-Authenticate": "Bearer"}


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    display_name: str
    role: Literal["beekeeper", "admin"]
    notify_email: bool
    ntfy_topic: str | None


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


class Db:
    """The request's database transaction, opened on first use.

    Requests that fail before they need the database (no token, invalid body) never take a connection,
    so unauthenticated traffic cannot drain the pool.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._conn: AsyncConnection | None = None

    async def execute(self, statement: TextClause, params: dict[str, Any] | None = None) -> CursorResult[Any]:
        if self._conn is None:
            self._conn = await self._engine.connect()
            await self._conn.begin()
        return await self._conn.execute(statement, params)

    async def finish(self, commit: bool) -> None:
        if self._conn is None:
            return
        try:
            await (self._conn.commit() if commit else self._conn.rollback())
        finally:
            await self._conn.close()


async def get_db(request: Request) -> AsyncIterator[Db]:
    """One transaction per request: it commits when the route returns and rolls back when it raises."""
    db = Db(request.app.state.engine)
    try:
        yield db
    except BaseException:
        await db.finish(commit=False)
        raise
    else:
        await db.finish(commit=True)


Conn = Annotated[Db, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


async def current_user(
    conn: Conn,
    settings: Config,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise Problem(401, "Not authenticated", headers=_UNAUTHENTICATED)
    try:
        claims = decode_access_token(settings.jwt_secret, credentials.credentials)
    except InvalidToken:
        raise Problem(401, "Invalid or expired token", headers=_UNAUTHENTICATED) from None
    row = (
        await conn.execute(
            text("SELECT id, email, display_name, role, notify_email, ntfy_topic FROM users WHERE id = :id"),
            {"id": claims.user_id},
        )
    ).first()
    if row is None:  # the user was deleted after the token was issued
        raise Problem(401, "Invalid or expired token", headers=_UNAUTHENTICATED)
    return User(row.id, row.email, row.display_name, row.role, row.notify_email, row.ntfy_topic)


CurrentUser = Annotated[User, Depends(current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise Problem(403, "Administrator role required")
    return user


Admin = Annotated[User, Depends(require_admin)]
