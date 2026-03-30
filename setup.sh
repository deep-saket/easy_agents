#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case ":${PYTHONPATH:-}:" in
  *":${ROOT_DIR}/src:"*) ;;
  *)
    export PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
    ;;
esac

echo "PYTHONPATH configured: ${PYTHONPATH}"
