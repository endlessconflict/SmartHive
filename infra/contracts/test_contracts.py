"""Every valid example passes its schema and every invalid one fails. Run: python -m pytest infra/contracts"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

HERE = Path(__file__).parent
SCHEMAS = {p.name.removesuffix(".schema.json"): json.loads(p.read_text()) for p in HERE.glob("*.schema.json")}
VALID = sorted((HERE / "examples/valid").glob("*.json"))
INVALID = sorted((HERE / "examples/invalid").glob("*.json"))


def check(path):
    # file name is <schema>.json or <schema>_<what is wrong>.json; schema names may contain "_" (cmd_ack)
    name = max((s for s in SCHEMAS if path.stem == s or path.stem.startswith(s + "_")), key=len)
    errors = list(Draft202012Validator(SCHEMAS[name]).iter_errors(json.loads(path.read_text())))
    return errors


@pytest.mark.parametrize("schema", SCHEMAS)
def test_schema_is_valid(schema):
    Draft202012Validator.check_schema(SCHEMAS[schema])


def test_every_schema_has_a_valid_example():
    assert {p.stem for p in VALID} == set(SCHEMAS)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_example_passes(path):
    assert check(path) == []


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_example_fails(path):
    assert check(path)
