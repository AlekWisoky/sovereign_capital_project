#!/usr/bin/env python3

"""Replay/backtest a JSONL dump of Victor AI Bot snapshots.

Example:

  python backend/scripts/backtest_replay.py --input snapshots.jsonl

The input is expected to be a JSONL file where each line is a JSON object
containing an `opportunities` list (directly or under `state.opportunities`).

This tool is deterministic and produces an *expected* PnL proxy based on
precomputed meta (profit_after_costs_wei and p_success).
"""

import argparse
import json
import os
import sys

# Ensure `backend/` is on sys.path when running as a script.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from victor_ai_bot.backtest.replay import replay_jsonl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to JSONL snapshot dump")
    ap.add_argument("--max-lines", type=int, default=0, help="Optional cap on number of lines")
    ap.add_argument("--output", default="", help="Optional path to write report JSON")
    args = ap.parse_args()

    report = replay_jsonl(args.input, max_lines=int(args.max_lines or 0))
    out = {
        "ticks": report.ticks,
        "trades": report.trades,
        "expected_profit_wei": str(report.expected_profit_wei),
        "avg_expected_profit_wei": str(report.avg_expected_profit_wei),
        "win_rate_proxy": report.win_rate_proxy,
        "by_route": report.by_route,
        "runtime": report.runtime,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, sort_keys=True)
        print(f"Wrote report to {args.output}")
    else:
        print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
