from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_render_system_truth_check_reports_fresh_repo_truth():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ['python', 'scripts/render_system_truth.py', '--check'],
        cwd=root,
        env={**os.environ, 'PYTHONPATH': 'backend'},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        import json
        from victor_ai_bot.system_truth import build_system_truth, truth_freshness_snapshot
        live = truth_freshness_snapshot(build_system_truth())
        docs = json.loads(
            (root / 'docs' / 'generated' / 'system_truth.json').read_text(encoding='utf-8')
        )
        written = truth_freshness_snapshot(docs)
        diff = {
            key: {'written': written.get(key), 'live': live.get(key)}
            for key in sorted(set(live) | set(written))
            if written.get(key) != live.get(key)
        }
        raise AssertionError((result.stdout + result.stderr) + "\ntruth_diff=" + json.dumps(diff, sort_keys=True))

    payload = json.loads(result.stdout)
    assert payload['ok'] is True
    assert payload['route_count'] > 0
    assert payload['backend_broad_except_count'] > 0
    assert payload['runtime_legacy_lines'] > 0
    assert payload['api_legacy_lines'] > 0
    assert payload['backend_test_file_count'] >= 1
