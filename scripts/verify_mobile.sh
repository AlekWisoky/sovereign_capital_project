#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/mobile"

echo "[1/3] node/npm presence"
if command -v node >/dev/null 2>&1; then node -v; else echo "node_not_found"; fi
if command -v npm >/dev/null 2>&1; then npm -v; else echo "npm_not_found"; fi

echo "[2/3] source tree sanity"
[ -f "package.json" ]
[ -d "src" ]
[ -f "src/state/store.tsx" ]
[ -f "src/navigation/MainTabs.tsx" ]

echo "[3/3] optional typecheck (requires node_modules)"
if [ -d "node_modules" ] && command -v npx >/dev/null 2>&1; then
  npx tsc --noEmit
else
  echo "skipped_tsc (run: cd mobile && npm install && npx tsc --noEmit)"
fi

echo "verify_mobile_ok"
