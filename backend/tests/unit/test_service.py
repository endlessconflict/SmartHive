from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.ingest import service


async def test_process_retries_transient_errors_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def flaky(engine: Any, topic: str, payload: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionRefusedError("database is down")

    monkeypatch.setattr(service, "ingest", flaky)
    await service.process(None, "t", b"{}", sleep=0)  # type: ignore[arg-type]
    assert calls == 3


async def test_process_swallows_a_permanent_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(engine: AsyncEngine, topic: str, payload: bytes) -> None:
        raise ValueError("boom")

    monkeypatch.setattr(service, "ingest", broken)
    await service.process(None, "t", b"{}", sleep=0)  # type: ignore[arg-type]
