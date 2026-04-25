from __future__ import annotations

import argparse
import json
import os

from .episode_builder import export_episodes_jsonl
from .replay.bundle import export_replay_bundle, load_replay_bundle
from .replay.verifier import verify_replay_bundle


def main() -> int:
    ap = argparse.ArgumentParser(description="x∆v RFT tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build_episodes")
    p_build.add_argument("--data-dir", required=True)
    p_build.add_argument("--out", required=True)
    p_build.add_argument("--limit", type=int, default=0)
    p_build.add_argument("--top-k", type=int, default=20)

    p_export = sub.add_parser("export_replay")
    p_export.add_argument("--data-dir", required=True)
    p_export.add_argument("--event-id", required=True)
    p_export.add_argument("--out", required=True)

    p_verify = sub.add_parser("verify_replay")
    p_verify.add_argument("--bundle", required=True)

    args = ap.parse_args()
    if args.cmd == "build_episodes":
        res = export_episodes_jsonl(args.data_dir, args.out, limit=args.limit, top_k=args.top_k)
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0
    if args.cmd == "export_replay":
        res = export_replay_bundle(args.data_dir, args.event_id, args.out)
        print(
            json.dumps(
                {"ok": True, "event_id": res.get("event_id"), "path": args.out},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.cmd == "verify_replay":
        with open(args.bundle, "r", encoding="utf-8") as f:
            bundle = json.load(f)
        print(json.dumps(verify_replay_bundle(bundle), indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
