"""A client that has its 201 must be able to read what it wrote: the transaction commits before the response."""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.app import create_app
from smarthive.api.deps import Db
from smarthive.config import Settings
from tests.integration.test_alerts import auth
from tests.integration.test_api_auth import SECRET, add_user

pytestmark = pytest.mark.integration


async def test_the_transaction_commits_before_the_response_starts(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await add_user(engine, "commit-order@example.com")
    app = create_app(Settings(jwt_secret=SECRET), engine)
    events: list[str] = []
    finish = Db.finish

    async def recording_finish(self: Db, commit: bool) -> None:
        await finish(self, commit)
        events.append("commit" if commit else "rollback")

    monkeypatch.setattr(Db, "finish", recording_finish)

    body = json.dumps({"name": "Commit order"}).encode()
    headers = [(k.lower().encode(), v.encode()) for k, v in auth(owner).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/v1/apiaries",
        "raw_path": b"/api/v1/apiaries",
        "query_string": b"",
        "headers": [*headers, (b"content-type", b"application/json"), (b"host", b"api.test")],
        "client": ("127.0.0.1", 1),
        "server": ("api.test", 443),
    }
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
        events.append(str(message["type"]))

    await app(scope, receive, send)  # type: ignore[arg-type]
    assert events.index("commit") < events.index("http.response.start"), events
