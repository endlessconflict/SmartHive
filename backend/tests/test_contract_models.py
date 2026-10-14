"""The generated Pydantic models accept every valid contract example.

Regenerate the models with infra/contracts/generate-models.sh.
"""

import json
from importlib import import_module
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parents[2] / "infra/contracts/examples/valid"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.stem)
def test_model_accepts_example(path):
    module = import_module(f"smarthive.contracts.{path.stem}_schema")
    getattr(module, path.stem.title().replace("_", "")).model_validate(json.loads(path.read_text()))
