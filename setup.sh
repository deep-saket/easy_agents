#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  SCRIPT_PATH="${BASH_SOURCE[0]}"
else
  SCRIPT_PATH="$0"
fi

ROOT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"

case ":${PYTHONPATH:-}:" in
  *":${ROOT_DIR}:${ROOT_DIR}/src:"*) ;;
  *)
    export PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
    ;;
esac

echo "PYTHONPATH configured: ${PYTHONPATH}"
