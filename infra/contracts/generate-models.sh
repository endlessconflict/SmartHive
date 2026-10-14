#!/usr/bin/env bash
# Regenerate backend/src/smarthive/contracts from the JSON Schemas. CI fails if the committed files differ.
# Needs: pip install datamodel-code-generator==0.83.0 ruff
set -euo pipefail
cd "$(dirname "$0")/../.."
out=backend/src/smarthive/contracts
rm -rf "$out"
# only the schemas as input: the examples and tests next to them are not part of the model
tmp=$(mktemp -d)/schemas  # fixed basename: it is written into the generated header
mkdir -p "$tmp"
cp infra/contracts/*.schema.json "$tmp"
datamodel-codegen --input "$tmp" --input-file-type jsonschema --output "$out" \
  --output-model-type pydantic_v2.BaseModel --disable-timestamp --target-python-version 3.11 --formatters ruff-format
rm -rf "$(dirname "$tmp")"
