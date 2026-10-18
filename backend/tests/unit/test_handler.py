import json
from pathlib import Path

import pytest

from smarthive.ingest.base import Rejected
from smarthive.ingest.handler import MAX_PAYLOAD_BYTES, validate

FIXTURE = (Path(__file__).parents[1] / "fixtures/telemetry_valid.json").read_bytes()
TOPIC = "smarthive/v1/nodes/node-0001/telemetry"


def test_valid_payload_passes() -> None:
    assert len(validate(TOPIC, FIXTURE).message.readings) == 3


@pytest.mark.parametrize(
    ("topic", "payload", "reason"),
    [
        pytest.param(TOPIC, b"{not json", "not_json", id="broken_json"),
        pytest.param(TOPIC, b"\xff\xfe\x00", "not_utf8", id="not_utf8"),
        pytest.param(TOPIC, b"[1, 2, 3]", "not_a_json_object", id="json_array"),
        pytest.param(TOPIC, b"x" * (MAX_PAYLOAD_BYTES + 1), "payload_too_large", id="too_large"),
        pytest.param(TOPIC, b"[" * 100_000, "not_json", id="nesting_too_deep"),
        pytest.param(
            "smarthive/v1/nodes/node-0001/config", FIXTURE, "unexpected_topic", id="not_a_node_topic"
        ),
        pytest.param(
            "smarthive/v1/nodes/node-0001/events", FIXTURE, "schema_violation", id="wrong_schema_for_topic"
        ),
        pytest.param("smarthive/v1/nodes/bad node/telemetry", FIXTURE, "unexpected_topic", id="odd_node_id"),
        pytest.param(
            "smarthive/v1/nodes/node-0002/telemetry", FIXTURE, "node_id_mismatch", id="node_mismatch"
        ),
        pytest.param(
            TOPIC, b'{"schema": "smarthive.telemetry/1.0"}', "schema_violation", id="fields_missing"
        ),
    ],
)
def test_rejections(topic: str, payload: bytes, reason: str) -> None:
    with pytest.raises(Rejected) as e:
        validate(topic, payload)
    assert e.value.reason == reason


def test_rejection_reports_at_most_five_errors_and_the_msg_id() -> None:
    doc = json.loads(FIXTURE)
    doc["readings"] = [{"ts": "x"}] * 20
    with pytest.raises(Rejected) as e:
        validate(TOPIC, json.dumps(doc).encode())
    assert len(e.value.errors) == 5
    assert e.value.msg_id == doc["msg_id"]
