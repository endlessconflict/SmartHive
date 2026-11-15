#!/usr/bin/env bash
# Regenerates the screenshots in guide/img from the running demo stack (needs Docker, nothing else).
cd "$(dirname "$0")"
mkdir -p img
MSYS_NO_PATHCONV=1 docker run --rm --add-host=host.docker.internal:host-gateway \
  -v "$(pwd -W 2>/dev/null || pwd):/g:ro" -v "$(cd img && (pwd -W 2>/dev/null || pwd)):/out" \
  mcr.microsoft.com/playwright:v1.50.0-noble \
  bash -c "cd /tmp && npm i playwright@1.50.0 >/dev/null 2>&1 && cp /g/shot.mjs . && node shot.mjs /out"
