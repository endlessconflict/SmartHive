from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.config import Settings
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


def test_tls_is_off_without_a_ca() -> None:
    assert service.tls_parameters(Settings(mqtt_tls_ca=None)) is None


def test_tls_parameters_carry_the_client_certificate() -> None:
    params = service.tls_parameters(
        Settings(mqtt_tls_ca="ca.crt", mqtt_tls_cert="b.crt", mqtt_tls_key="b.key")
    )
    assert params is not None
    assert (params.ca_certs, params.certfile, params.keyfile) == ("ca.crt", "b.crt", "b.key")


def test_tls_server_only_is_still_allowed() -> None:
    params = service.tls_parameters(Settings(mqtt_tls_ca="ca.crt"))
    assert params is not None and params.certfile is None


@pytest.mark.parametrize("cert,key", [("b.crt", None), (None, "b.key")])
def test_tls_certificate_without_its_key_is_a_configuration_error(cert: str | None, key: str | None) -> None:
    with pytest.raises(ValueError, match="together"):
        service.tls_parameters(Settings(mqtt_tls_ca="ca.crt", mqtt_tls_cert=cert, mqtt_tls_key=key))
