#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/5] import boot check"
PYTHONPATH=backend python -c "from victor_ai_bot.server import app; print('boot_ok')"

echo "[2/5] generated system truth freshness"
PYTHONPATH=backend python scripts/render_system_truth.py --check

echo "[3/5] optional family reachability freshness"
PYTHONPATH=backend python scripts/render_optional_family_status.py --check

echo "[4/5] unit tests"
cd backend
PYTHONPATH=. pytest -q

echo "[5/5] rpc config sanity"
cd ..
PYTHONPATH=backend python scripts/verify_rpcs.py --config "${VICTOR_CONFIG:-backend/config/ethereum.yaml}" --json >/dev/null || true

echo "verify_boot_ok"
