#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${ROOT_DIR}/.venv"

cd "$ROOT_DIR"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -c backend/constraints.txt -r backend/requirements-dev.txt

if command -v npm >/dev/null 2>&1; then
  cd "$ROOT_DIR/mobile"
  npm install --no-fund --no-audit
else
  echo "npm_not_found: install Node.js 18+ to bootstrap mobile dependencies" >&2
fi

echo "bootstrap_local_ok"
