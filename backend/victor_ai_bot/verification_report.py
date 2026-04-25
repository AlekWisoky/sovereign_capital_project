from __future__ import annotations

import json
import os
import re
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .system_truth import ROOT, BACKEND_ROOT, MOBILE_ROOT, build_system_truth

CONTRACTS_ROOT = ROOT / 'contracts'
DOCS_ROOT = ROOT / 'docs'
GENERATED_DIR = DOCS_ROOT / 'generated'
WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'ci.yml'
PYPROJECT_PATH = ROOT / 'pyproject.toml'
SMOOTH_RUN_REVIEW_PATH = DOCS_ROOT / 'SMOOTH_RUN_REVIEW.md'


def _generated_ts_ms() -> int:
    src = os.environ.get('SOURCE_DATE_EPOCH')
    if src:
        try:
            return int(float(src) * 1000)
        except (TypeError, ValueError, OverflowError):
            pass
    return int(time.time() * 1000)


def _generated_ts_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat().replace('+00:00', 'Z')


def _load_pyproject() -> dict:
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding='utf-8'))


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding='utf-8')


def _inventory(root: Path, pattern: str) -> List[str]:
    return sorted(str(p.relative_to(ROOT)) for p in root.rglob(pattern))


def _extract_ci_mypy_targets(workflow_text: str) -> List[str]:
    lines = workflow_text.splitlines()
    targets: List[str] = []
    collecting = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("mypy "):
            collecting = True
            stripped = stripped[len("mypy "):]
        elif not collecting:
            continue
        elif not stripped:
            break
        part = stripped.rstrip("\\").strip()
        if part:
            targets.append(part)
        if not stripped.endswith("\\"):
            break
    return targets


def _coverage_summary(pyproject: dict, workflow_text: str) -> Dict[str, Any]:
    ruff = ((pyproject.get('tool') or {}).get('ruff') or {})
    black = ((pyproject.get('tool') or {}).get('black') or {})
    ruff_excludes = list(ruff.get('extend-exclude') or [])
    black_excludes = [line.strip() for line in str(black.get('extend-exclude') or '').splitlines() if line.strip().startswith('|^/backend') or line.strip().startswith('^/backend')]
    mypy_targets = _extract_ci_mypy_targets(workflow_text)
    return {
        'ruff': {
            'enabled_in_ci': 'ruff check backend' in workflow_text,
            'excluded_domains': ruff_excludes,
        },
        'black': {
            'enabled_in_ci': 'black --check backend' in workflow_text,
            'excluded_domains': black_excludes,
        },
        'mypy': {
            'enabled_in_ci': 'mypy ' in workflow_text,
            'targets': mypy_targets,
        },
        'staged_expansion': {
            'fioa_shell_lint_domain_enabled': 'backend/victor_ai_bot/fioa/__init__.py' in mypy_targets or 'backend/victor_ai_bot/fioa/config.py' in mypy_targets,
            'execution_facade_type_targets': [
                x for x in mypy_targets
                if 'runtime_execute_' in x or x.endswith('/execution.py')
            ],
        },
    }


def _critical_hardening_tests(backend_tests: List[str]) -> Dict[str, Any]:
    categories = {
        'runtime_compatibility': [x for x in backend_tests if 'runtime_' in Path(x).name or 'execution_service_auto_trade_hold' in x],
        'execution_hardening': [x for x in backend_tests if 'execution' in Path(x).name],
        'capital_and_fund_truth': [x for x in backend_tests if any(tok in Path(x).name for tok in ('ledger', 'fund', 'capital', 'prime', 'portfolio'))],
    }
    return {
        'counts': {k: len(v) for k, v in categories.items()},
        'files': categories,
    }


def build_verification_report() -> Dict[str, Any]:
    ts_ms = _generated_ts_ms()
    ts_iso = _generated_ts_iso(ts_ms)
    system_truth = build_system_truth()
    pyproject = _load_pyproject()
    workflow_text = _workflow_text()

    backend_tests = _inventory(BACKEND_ROOT / 'tests', 'test_*.py')
    mobile_tests = _inventory(MOBILE_ROOT / 'tests', '*.test.ts')
    contract_tests = _inventory(CONTRACTS_ROOT / 'test', '*.sol')
    mobile_package = json.loads((MOBILE_ROOT / 'package.json').read_text(encoding='utf-8'))

    report = {
        'generated_at': ts_iso,
        'generated_at_ms': ts_ms,
        'generated_at_iso': ts_iso,
        'generator': 'scripts/render_verification_report.py',
        'source_of_truth': [
            'pyproject.toml',
            '.github/workflows/ci.yml',
            'docs/generated/system_truth.json',
            'backend test inventory',
            'mobile/package.json',
            'contracts/test inventory',
        ],
        'backend': {
            'test_file_count': len(backend_tests),
            'test_files': backend_tests,
            'pytest_command': 'cd backend && pytest -q',
        },
        'critical_hardening': _critical_hardening_tests(backend_tests),
        'mobile': {
            'test_file_count': len(mobile_tests),
            'test_files': mobile_tests,
            'ci_script': str((mobile_package.get('scripts') or {}).get('ci:test') or ''),
            'verification_status': 'inventory_and_ci_script',
        },
        'contracts': {
            'test_file_count': len(contract_tests),
            'test_files': contract_tests,
            'ci_command': 'cd contracts && forge test -q',
            'verification_status': 'inventory_and_ci_command',
        },
        'static_analysis': _coverage_summary(pyproject, workflow_text),
        'runtime_surface': {
            'route_count': system_truth['route_count'],
            'websocket_route_count': system_truth['websocket_route_count'],
            'runtime_legacy_lines': system_truth['runtime_legacy_lines'],
            'api_legacy_lines': system_truth['api_legacy_lines'],
            'backend_broad_except_count': system_truth['backend_broad_except_count'],
        },
        'verified': {
            'backend_inventory': True,
            'runtime_surface_summary': True,
            'ci_static_analysis_inventory': True,
            'contract_inventory': True,
            'mobile_inventory': True,
        },
        'partially_verified': {
            'mobile_runtime_behavior': 'requires node/npm environment',
            'contract_runtime_behavior': 'requires foundry environment',
            'static_analysis_excluded_domains': _coverage_summary(pyproject, workflow_text)['ruff']['excluded_domains'],
        },
        'out_of_scope': [
            'live wallet execution',
            'external RPC/provider uptime',
            'production-only mobile signing flows',
        ],
        'reproducibility': {
            'refresh_command': 'PYTHONPATH=backend python scripts/render_verification_report.py',
            'freshness_check_command': 'PYTHONPATH=backend python scripts/render_verification_report.py --check',
            'notes': 'Generated from live repository inventory and CI configuration. Does not claim manual pass counts.',
        },
    }
    return report


def _freshness_snapshot(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'backend_test_file_count': report['backend']['test_file_count'],
        'mobile_test_file_count': report['mobile']['test_file_count'],
        'contract_test_file_count': report['contracts']['test_file_count'],
        'runtime_surface': report['runtime_surface'],
        'critical_hardening_counts': report['critical_hardening']['counts'],
        'static_analysis': report['static_analysis'],
    }


def verification_report_is_fresh(existing: Dict[str, Any], live: Dict[str, Any]) -> bool:
    return _freshness_snapshot(existing) == _freshness_snapshot(live)


def _markdown(report: Dict[str, Any]) -> str:
    lines = [
        '<!-- AUTOGENERATED: do not edit by hand. Use scripts/render_verification_report.py -->',
        '# Generated Verification Report',
        '',
        f"Generated at: `{report['generated_at_iso']}`",
        f"Generator: `{report['generator']}`",
        '',
        '## Backend verification inventory',
        f"- Backend test files: **{report['backend']['test_file_count']}**",
        f"- Repro command: `{report['backend']['pytest_command']}`",
        '',
        '## Critical hardening tests',
    ]
    for key, count in report['critical_hardening']['counts'].items():
        lines.append(f"- {key}: **{count}**")
    lines += [
        '',
        '## Mobile / contracts',
        f"- Mobile test files: **{report['mobile']['test_file_count']}** ({report['mobile']['verification_status']})",
        f"- Contracts test files: **{report['contracts']['test_file_count']}** ({report['contracts']['verification_status']})",
        '',
        '## Static analysis coverage summary',
        f"- Ruff in CI: **{report['static_analysis']['ruff']['enabled_in_ci']}**",
        f"- Black in CI: **{report['static_analysis']['black']['enabled_in_ci']}**",
        f"- Mypy in CI: **{report['static_analysis']['mypy']['enabled_in_ci']}**",
        f"- Mypy targets: `{', '.join(report['static_analysis']['mypy']['targets'])}`",
        '',
        '## Runtime surface summary',
        f"- Route count: **{report['runtime_surface']['route_count']}**",
        f"- WebSocket routes: **{report['runtime_surface']['websocket_route_count']}**",
        f"- Runtime legacy lines: **{report['runtime_surface']['runtime_legacy_lines']}**",
        f"- Backend broad exception count: **{report['runtime_surface']['backend_broad_except_count']}**",
        '',
        '## Verification status',
        '- Verified: repository inventory, CI-configured static-analysis coverage, runtime surface counts',
        '- Partially verified: mobile runtime behavior and contracts runtime behavior require their native toolchains',
        '- Out of scope: live wallets, external RPC/provider uptime, production-only signing flows',
        '',
        '## Reproducibility',
        f"- Refresh: `{report['reproducibility']['refresh_command']}`",
        f"- Freshness check: `{report['reproducibility']['freshness_check_command']}`",
        f"- Notes: {report['reproducibility']['notes']}",
        '',
        '> This report replaces stale hand-written smooth-run confidence claims with generated repository truth.',
        '',
    ]
    return '\n'.join(lines)


def write_verification_report(out_dir: Path | None = None) -> Dict[str, Any]:
    report = build_verification_report()
    target_dir = Path(out_dir) if out_dir is not None else GENERATED_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / 'verification_report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    md = _markdown(report)
    (target_dir / 'verification_report.md').write_text(md, encoding='utf-8')
    SMOOTH_RUN_REVIEW_PATH.write_text(md, encoding='utf-8')
    return report
