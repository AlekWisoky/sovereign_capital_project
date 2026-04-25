#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from victor_ai_bot.system_truth import build_system_truth, generated_truth_is_fresh, write_system_truth


def _build_summary(out: dict) -> dict:
    return {
        'ok': True,
        'generated_at': out['generated_at'],
        'generated_at_ms': out['generated_at_ms'],
        'generated_at_iso': out['generated_at_iso'],
        'route_count': out['route_count'],
        'duplicate_route_count': out['duplicate_route_count'],
        'runtime_legacy_lines': out['runtime_legacy_lines'],
        'api_legacy_lines': out['api_legacy_lines'],
        'backend_broad_except_count': out['backend_broad_except_count'],
        'backend_test_file_count': out['backend_test_file_count'],
        'mobile_test_file_count': out['mobile_test_file_count'],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Verify docs/generated/system_truth.* matches live repo state')
    args = parser.parse_args()

    if args.check:
        live = build_system_truth()
        docs_path = ROOT / 'docs' / 'generated' / 'system_truth.json'
        try:
            existing = json.loads(docs_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            print(json.dumps({'ok': False, 'reason': 'missing_generated_truth', 'path': str(docs_path)}))
            return 1
        if not generated_truth_is_fresh(existing, live):
            print(json.dumps({
                'ok': False,
                'reason': 'stale_generated_truth',
                'path': str(docs_path),
                'live_summary': _build_summary(live),
                'written_summary': _build_summary(existing),
            }, sort_keys=True))
            return 1
        print(json.dumps(_build_summary(live), sort_keys=True))
        return 0

    out = write_system_truth()
    print(json.dumps(_build_summary(out), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
