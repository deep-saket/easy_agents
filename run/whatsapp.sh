#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "./setup.sh" ]]; then
  # shellcheck disable=SC1091
  source ./setup.sh
fi

HOST="${WHATSAPP_ENDPOINT_HOST:-0.0.0.0}"
PORT="${WHATSAPP_ENDPOINT_PORT:-8010}"

if command -v lsof >/dev/null 2>&1; then
  EXISTING_PIDS="$(lsof -ti tcp:"$PORT" || true)"
  if [[ -n "$EXISTING_PIDS" ]]; then
    echo "Stopping processes on port $PORT: $EXISTING_PIDS"
    kill $EXISTING_PIDS || true
    sleep 1
  fi
fi

.venv/bin/uvicorn endpoints.whatsapp:app --host "$HOST" --port "$PORT"
