import random
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from smarthive import seeder
from smarthive.contracts.event import Event
from smarthive.contracts.health import Health
from smarthive.contracts.status import Status
from smarthive.contracts.summary import Summary
from smarthive.contracts.telemetry import Telemetry

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
CONTRACTS: dict[str, type[BaseModel]] = {
    "telemetry": Telemetry,
    "health": Health,
    "summary": Summary,
    "events": Event,
    "status": Status,
}


@pytest.mark.parametrize("scenario", seeder.SCENARIOS)
def test_every_message_validates_against_the_contract(scenario: str) -> None:
    out = seeder.messages("node-0001", "boot-1", NOW, scenario, random.Random(1))
    assert out
    for kind, payload, _ in out:
        model = CONTRACTS[kind].model_validate(payload)
        if kind != "status":
            assert payload["node_id"] == "node-0001" and model


def test_scenarios_carry_what_the_alert_rules_look_for() -> None:
    def kinds(s: str) -> dict[str, dict]:  # type: ignore[type-arg]
        return {k: p for k, p, _ in seeder.messages("n", "b", NOW, s, random.Random(1))}

    assert "events" in kinds("hornet") and "events" not in kinds("normal")
    low = Telemetry.model_validate(kinds("low-battery")["telemetry"])
    volts = [r.value for r in low.readings if r.quantity == "battery_v"]
    assert volts and all(v is not None and v < 10.2 for v in volts)
    assert kinds("low-battery")["health"]["throttled"]["under_voltage_now"] is True
    assert kinds("varroa")["summary"]["varroa"]["positive"] / 1800 > 0.1
    assert seeder.messages("n", "b", NOW, "offline", random.Random(1))[0][2] is True  # retained
