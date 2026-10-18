"""The API without a database: errors, liveness, readiness against a database that is down."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from smarthive.api.app import create_app
from smarthive.config import Settings


@pytest.fixture
async def client() -> httpx.AsyncClient:
    engine = create_async_engine(
        "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none"
    )  # nothing listens on port 1
    app = create_app(Settings(jwt_secret="s" * 40), engine)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="https://t"
    )


def test_the_api_refuses_to_start_without_a_secret() -> None:
    with pytest.raises(RuntimeError, match="SMARTHIVE_JWT_SECRET"):
        create_app(Settings(jwt_secret=""))


async def test_liveness_does_not_need_the_database(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_readiness_reports_a_down_database_as_a_problem(client: httpx.AsyncClient) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 503
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json() == {"type": "about:blank", "title": "Database unavailable", "status": 503}


async def test_an_unknown_path_is_a_problem_document(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/nothing")
    assert r.status_code == 404 and r.headers["content-type"] == "application/problem+json"
    assert set(r.json()) == {"type", "title", "status"}


async def test_validation_errors_list_the_fields(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": "a@b.c"})
    body = r.json()
    assert r.status_code == 422 and body["title"] == "Request validation failed"
    assert body["errors"][0]["loc"] == "body.password"


async def test_a_protected_route_asks_for_a_bearer_token(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/me")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


async def test_the_openapi_document_is_where_the_dashboard_expects_it(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    assert r.status_code == 200 and "/api/v1/auth/login" in r.json()["paths"]
