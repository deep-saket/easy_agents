#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CONSTELLATION_HOST="${CONSTELLATION_HOST:-127.0.0.1}"
CONSTELLATION_PORT="${CONSTELLATION_PORT:-8030}"

if command -v lsof >/dev/null 2>&1 \
  && lsof -tiTCP:"$CONSTELLATION_PORT" -sTCP:LISTEN >/dev/null; then
  echo "Port $CONSTELLATION_PORT is already in use. Set CONSTELLATION_PORT to another local port."
  exit 1
fi

.venv/bin/uvicorn endpoints.constellation:app \
  --host "$CONSTELLATION_HOST" \
  --port "$CONSTELLATION_PORT"
