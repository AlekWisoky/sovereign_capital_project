"""Smoke script: load config and print key overlay states.

This script does not require RPC connectivity unless you pass --start.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from victor_ai_bot.config import load_config
from victor_ai_bot.runtime import RuntimeBundle


async def _main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="backend/config/ethereum.yaml")
    ap.add_argument("--start", action="store_true", help="Start runtime loop briefly (requires RPC).")
    args = ap.parse_args()

    cfg = load_config(args.config)
    # RuntimeBundle derives its data directory from VICTOR_DATA_DIR.
    os.environ.setdefault("VICTOR_DATA_DIR", os.path.join(os.getcwd(), "backend", "data"))
    rt = RuntimeBundle(cfg)

    print("== behaveagent ==")
    print(json.dumps(rt.behaveagent_state(), indent=2))
    print("== treasury ==")
    print(json.dumps(rt.treasury_state(), indent=2))
    print("== governance ==")
    print(json.dumps(rt.governance_state(), indent=2))
    print("== consensus ==")
    print(json.dumps(rt.consensus_state(), indent=2))
    print("== unified ==")
    print(json.dumps(rt.unified_state(), indent=2))
    print("== spread ==")
    print(json.dumps(rt.spread_opportunities(), indent=2))
    print("== orchestrator ==")
    print(json.dumps(rt.orchestrator_state(), indent=2))
    print("== blockspace ==")
    print(json.dumps(rt.blockspace_state(), indent=2))

    if args.start:
        rt.start()
        await asyncio.sleep(5.0)
        await rt.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
