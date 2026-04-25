#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from victor_ai_bot.verification_report import build_verification_report, verification_report_is_fresh, write_verification_report


def _summary(report: dict) -> dict:
    return {
        'ok': True,
        'generated_at': report['generated_at'],
        'generated_at_ms': report['generated_at_ms'],
        'backend_test_file_count': report['backend']['test_file_count'],
        'mobile_test_file_count': report['mobile']['test_file_count'],
        'contract_test_file_count': report['contracts']['test_file_count'],
        'route_count': report['runtime_surface']['route_count'],
        'runtime_legacy_lines': report['runtime_surface']['runtime_legacy_lines'],
        'backend_broad_except_count': report['runtime_surface']['backend_broad_except_count'],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    if args.check:
        live = build_verification_report()
        docs_path = ROOT / 'docs' / 'generated' / 'verification_report.json'
        try:
            existing = json.loads(docs_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            print(json.dumps({'ok': False, 'reason': 'missing_generated_verification_report', 'path': str(docs_path)}))
            return 1
        if not verification_report_is_fresh(existing, live):
            print(json.dumps({
                'ok': False,
                'reason': 'stale_generated_verification_report',
                'path': str(docs_path),
                'live_summary': _summary(live),
                'written_summary': _summary(existing),
            }, sort_keys=True))
            return 1
        print(json.dumps(_summary(live), sort_keys=True))
        return 0

    report = write_verification_report()
    print(json.dumps(_summary(report), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
