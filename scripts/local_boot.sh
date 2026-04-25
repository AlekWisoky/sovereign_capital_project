#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${VICTOR_CONFIG:-$ROOT_DIR/backend/config/ethereum.yaml}"
HOST="${VICTOR_HOST:-0.0.0.0}"
PORT="${VICTOR_PORT:-8000}"

cd "$ROOT_DIR"
if [ ! -d .venv ]; then
  "$ROOT_DIR/scripts/bootstrap_local.sh"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT_DIR/backend"
exec python -m uvicorn victor_ai_bot.server:app --host "$HOST" --port "$PORT"
