#!/usr/bin/env sh
set -eu
PORT="${PORT:-8000}"
mkdir -p /app/backend/data /app/backend/data/state /app/backend/data/internal_prime /app/backend/data/execution_capture /app/backend/data/risk /app/backend/data/telemetry /app/backend/data/treasury /app/backend/data/fund_os
# Backward-compatible cleanup for older packaged layouts that accidentally nested runtime data under backend/backend/data.
if [ -d /app/backend/backend/data ]; then
  find /app/backend/backend/data -type f | while read -r oldf; do
    rel="${oldf#/app/backend/backend/data/}"
    newf="/app/backend/data/$rel"
    mkdir -p "$(dirname "$newf")"
    if [ ! -f "$newf" ]; then
      cp "$oldf" "$newf"
    fi
  done
fi
exec uvicorn victor_ai_bot.server:app --host 0.0.0.0 --port "$PORT"
