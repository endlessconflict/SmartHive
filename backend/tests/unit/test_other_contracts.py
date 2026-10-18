import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from smarthive.contracts.event import Event
from smarthive.contracts.health import Health
from smarthive.contracts.status import Status
from smarthive.contracts.summary import Summary

FIXTURES = Path(__file__).parents[1] / "fixtures"


def load(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return doc


def test_the_contract_examples_validate() -> None:
    assert Event.model_validate(load("event_threat.json")).event.cls == "hornet"
    assert Summary.model_validate(load("summary_valid.json")).varroa.positive == 41
    assert Health.model_validate(load("health_valid.json")).clock_synced is True


def test_unknown_event_fields_and_types_are_accepted() -> None:
    doc = load("event_threat.json")
    doc["event"]["type"] = "storage_low"
    doc["event"]["free_mb"] = 120
    doc["something_new"] = True
    assert Event.model_validate(doc).event.type == "storage_low"


@pytest.mark.parametrize("schema", ["smarthive.event/2.0", "smarthive.telemetry/1.0", "event/1.0"])
def test_the_schema_must_be_this_kind_and_major_version(schema: str) -> None:
    doc = load("event_threat.json")
    doc["schema"] = schema
    with pytest.raises(ValidationError):
        Event.model_validate(doc)


def test_an_episode_cannot_end_before_it_starts() -> None:
    doc = load("event_threat.json")
    doc["event"]["last_seen"] = "2026-10-06T14:00:00Z"
    with pytest.raises(ValidationError, match="last_seen"):
        Event.model_validate(doc)


@pytest.mark.parametrize("conf", [-0.1, 1.2])
def test_confidence_is_a_probability(conf: float) -> None:
    doc = load("event_threat.json")
    doc["event"]["max_conf"] = conf
    with pytest.raises(ValidationError):
        Event.model_validate(doc)


def test_more_positive_than_classified_bees_is_rejected() -> None:
    doc = load("summary_valid.json")
    doc["varroa"] = {"bees_classified": 10, "positive": 11}
    with pytest.raises(ValidationError, match="more Varroa-positive"):
        Summary.model_validate(doc)


def test_a_summary_window_must_have_a_positive_length() -> None:
    doc = copy.deepcopy(load("summary_valid.json"))
    doc["window"]["end"] = doc["window"]["start"]
    with pytest.raises(ValidationError, match="end after"):
        Summary.model_validate(doc)


def test_negative_counts_are_rejected() -> None:
    doc = load("summary_valid.json")
    doc["counts"]["bee"] = -1
    with pytest.raises(ValidationError):
        Summary.model_validate(doc)


def test_status_accepts_the_last_will_and_the_online_message() -> None:
    assert Status.model_validate({"state": "offline"}).reason is None
    assert Status.model_validate({"state": "online", "boot_id": "b1"}).boot_id == "b1"
    assert Status.model_validate({"state": "offline", "reason": "shutdown"}).reason == "shutdown"


def test_status_rejects_other_states() -> None:
    with pytest.raises(ValidationError):
        Status.model_validate({"state": "sleeping"})
