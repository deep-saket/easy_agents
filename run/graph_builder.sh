#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "./setup.sh" ]]; then
  # shellcheck disable=SC1091
  source ./setup.sh
fi

HOST="${GRAPH_BUILDER_HOST:-127.0.0.1}"
PORT="${GRAPH_BUILDER_PORT:-8020}"

if command -v lsof >/dev/null 2>&1; then
  EXISTING_PIDS="$(lsof -ti tcp:"$PORT" || true)"
  if [[ -n "$EXISTING_PIDS" ]]; then
    echo "Port $PORT is occupied. Stopping processes: $EXISTING_PIDS"
    kill $EXISTING_PIDS || true
    sleep 1

    REMAINING_PIDS="$(lsof -ti tcp:"$PORT" || true)"
    if [[ -n "$REMAINING_PIDS" ]]; then
      echo "Forcing stop on port $PORT: $REMAINING_PIDS"
      kill -9 $REMAINING_PIDS || true
      sleep 1
    fi
  fi
fi

.venv/bin/uvicorn endpoints.graph_builder:app --host "$HOST" --port "$PORT" --reload
