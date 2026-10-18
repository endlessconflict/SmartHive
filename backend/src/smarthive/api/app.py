"""The FastAPI application. `create_app()` is a factory, so tests pass their own settings and database."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from smarthive.api import errors
from smarthive.api.ratelimit import FailureLimiter
from smarthive.api.routes import apiaries, auth, health, me
from smarthive.config import Settings


def create_app(settings: Settings | None = None, engine: AsyncEngine | None = None) -> FastAPI:
    settings = settings or Settings()
    if not settings.jwt_secret:
        raise RuntimeError("SMARTHIVE_JWT_SECRET is empty: set a long random string before starting the API")
    owns_engine = engine is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not hasattr(app.state, "engine"):
            app.state.engine = create_async_engine(settings.db_url, pool_pre_ping=True)
        try:
            yield
        finally:
            if owns_engine:
                await app.state.engine.dispose()

    app = FastAPI(
        title="SmartHive API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    if engine is not None:
        app.state.engine = engine
    app.state.login_limiter = FailureLimiter(settings.login_max_failures, settings.login_window_s)
    errors.install(app)
    for module in (health, auth, me, apiaries):
        app.include_router(module.router)
    return app
