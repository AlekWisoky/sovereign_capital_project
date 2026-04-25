from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_render_optional_family_status_check_reports_fresh_repo_truth() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["python", "scripts/render_optional_family_status.py", "--check"],
        cwd=root,
        env={**os.environ, "PYTHONPATH": "backend"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["classificationEngine"] == "automatic_runtime_reachability_v3"
    assert payload["familyCount"] >= 1
    assert set(payload["statusCounts"]) == {"dead", "live", "shadow", "staged"}
