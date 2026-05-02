#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/saketm10/Projects/openclaw_agents"
CONDA_SH="/Users/saketm10/miniconda3/etc/profile.d/conda.sh"
ENV_NAME="ecs"

cd "$ROOT_DIR"

if [[ ! -f "$CONDA_SH" ]]; then
  echo "Conda init script not found at: $CONDA_SH" >&2
  exit 1
fi

source "$CONDA_SH"
conda activate "$ENV_NAME"

set -a
source .env
set +a

python -m agents.collection_agent.ui.server
