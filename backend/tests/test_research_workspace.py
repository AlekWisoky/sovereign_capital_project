from __future__ import annotations

import json
from pathlib import Path

from victor_ai_bot.research_pipeline.workspace import ResearchWorkspace


def test_research_workspace_recovers_from_corrupt_json(tmp_path: Path):
    data_dir = tmp_path / "data"
    workspace_path = data_dir / "research" / "workspace_eth.json"
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    workspace_path.write_text("{not valid json", encoding="utf-8")

    workspace = ResearchWorkspace(data_dir=str(data_dir), chain="eth")

    snap = workspace.snapshot()
    assert snap["chain"] == "eth"
    assert "notesEnabled" not in snap
    assert snap["pipelineCounts"]["sandbox"] == 0
    assert snap["throughput"]["candidatesGenerated"] == 0


def test_research_workspace_sanitizes_partial_state(tmp_path: Path):
    data_dir = tmp_path / "data"
    workspace_path = data_dir / "research" / "workspace_base.json"
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    workspace_path.write_text(
        json.dumps(
            {
                "chain": 7,
                "createdTs": "42",
                "notesEnabled": "yes",
                "notes": ["bad"],
                "owner": "alice",
                "updatedTs": "17",
                "junk": {"x": 1},
            }
        ),
        encoding="utf-8",
    )

    workspace = ResearchWorkspace(data_dir=str(data_dir), chain="base")

    snap = workspace.snapshot()
    assert snap["chain"] == "7"
    assert snap["createdTs"] == 42
    assert snap["notesEnabled"] is True
    assert snap["owner"] == "alice"
    assert snap["updatedTs"] == 17
    assert "notes" not in snap
    assert "junk" not in snap
