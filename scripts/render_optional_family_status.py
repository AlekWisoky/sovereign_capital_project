#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from victor_ai_bot.optional_family_status import (
    OUT_JSON,
    build_optional_family_status,
    build_optional_family_status_summary,
    optional_family_status_is_fresh,
    write_optional_family_status,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        live = build_optional_family_status()
        try:
            existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "reason": "missing_generated_optional_family_status",
                        "path": str(OUT_JSON),
                    }
                )
            )
            return 1
        if not optional_family_status_is_fresh(existing, live):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "reason": "stale_generated_optional_family_status",
                        "path": str(OUT_JSON),
                        "live_summary": build_optional_family_status_summary(live),
                        "written_summary": build_optional_family_status_summary(existing),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(build_optional_family_status_summary(live), sort_keys=True))
        return 0

    payload = write_optional_family_status()
    print(json.dumps(build_optional_family_status_summary(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
