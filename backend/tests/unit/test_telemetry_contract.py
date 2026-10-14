import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from smarthive.contracts.telemetry import Telemetry

VALID: dict[str, Any] = json.loads((Path(__file__).parents[1] / "fixtures/telemetry_valid.json").read_text())


def mutated(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    doc = copy.deepcopy(VALID)
    change(doc)
    return doc


def set_reading(key: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def change(doc: dict[str, Any]) -> None:
        doc["readings"][0][key] = value

    return change


def test_valid_fixture_validates() -> None:
    t = Telemetry.model_validate(VALID)
    assert t.node_id == "node-0001"
    assert [r.value for r in t.readings] == [35.0, 58.0, None]


def test_unknown_fields_and_unknown_minor_are_accepted() -> None:
    doc = mutated(lambda d: d.update({"schema": "smarthive.telemetry/1.7", "future": 1}))
    doc["readings"][0]["extra"] = "x"
    assert Telemetry.model_validate(doc)


def test_unknown_quantity_is_accepted() -> None:
    doc = mutated(set_reading("quantity", "co2_ppm"))
    doc["readings"][0]["unit"] = "ppm"
    assert Telemetry.model_validate(doc).readings[0].quantity == "co2_ppm"


# One case per rule in the validation table of the task brief
INVALID: dict[str, dict[str, Any]] = {
    "schema_missing": mutated(lambda d: d.pop("schema")),
    "schema_other_family": mutated(lambda d: d.update({"schema": "smarthive.event/1.0"})),
    "schema_major_2": mutated(lambda d: d.update({"schema": "smarthive.telemetry/2.0"})),
    "msg_id_not_uuid": mutated(lambda d: d.update({"msg_id": "not-a-uuid"})),
    "msg_id_missing": mutated(lambda d: d.pop("msg_id")),
    "node_id_empty": mutated(lambda d: d.update({"node_id": ""})),
    "boot_id_missing": mutated(lambda d: d.pop("boot_id")),
    "sent_at_missing": mutated(lambda d: d.pop("sent_at")),
    "sent_at_naive": mutated(lambda d: d.update({"sent_at": "2026-10-06T14:05:00"})),
    "readings_empty": mutated(lambda d: d.update({"readings": []})),
    "readings_too_many": mutated(lambda d: d.update({"readings": d["readings"][:1] * 5001})),
    "readings_not_a_list": mutated(lambda d: d.update({"readings": {}})),
    "ts_naive": mutated(set_reading("ts", "2026-10-06T14:04:00")),
    "ts_garbage": mutated(set_reading("ts", "yesterday")),
    "mono_ms_negative": mutated(set_reading("mono_ms", -1)),
    "mono_ms_string": mutated(set_reading("mono_ms", "7")),
    "clock_synced_not_bool": mutated(set_reading("clock_synced", "true")),
    "sensor_empty": mutated(set_reading("sensor", "")),
    "quantity_empty": mutated(set_reading("quantity", "")),
    "unit_empty": mutated(set_reading("unit", "")),
    "unit_mismatch": mutated(set_reading("unit", "degF")),
    "quality_unknown": mutated(set_reading("quality", "great")),
    "value_nan": mutated(set_reading("value", float("nan"))),
    "value_infinite": mutated(set_reading("value", float("inf"))),
    "value_string": mutated(set_reading("value", "35")),
    "value_bool": mutated(set_reading("value", True)),
    "value_null_but_ok": mutated(set_reading("value", None)),
}


@pytest.mark.parametrize("doc", INVALID.values(), ids=INVALID.keys())
def test_invalid_payload_is_rejected(doc: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Telemetry.model_validate(doc)
