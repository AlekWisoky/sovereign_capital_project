from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_render_verification_report_check_reports_fresh_repo_truth():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ['python', 'scripts/render_verification_report.py', '--check'],
        cwd=root,
        env={**os.environ, 'PYTHONPATH': 'backend'},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload['ok'] is True
    assert payload['backend_test_file_count'] >= 1
    assert payload['route_count'] > 0
    assert payload['backend_broad_except_count'] >= 0
