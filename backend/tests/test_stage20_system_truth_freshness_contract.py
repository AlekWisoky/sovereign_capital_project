import json
from pathlib import Path

from victor_ai_bot.system_truth import build_system_truth


def test_system_truth_exposes_plain_generated_at_aliases():
    truth = build_system_truth()
    assert truth["generated_at"] == truth["generated_at_iso"]
    assert truth["generatedAt"] == truth["generatedAtIso"]
    assert truth["generated_at"].endswith("Z")


def test_generated_docs_expose_internal_freshness_alias_consistency():
    root = Path(__file__).resolve().parents[2]
    docs_truth = json.loads((root / "docs" / "generated" / "system_truth.json").read_text(encoding="utf-8"))
    assert docs_truth["generated_at"] == docs_truth["generated_at_iso"]
    assert docs_truth["generatedAt"] == docs_truth["generatedAtIso"]
    assert docs_truth["generated_at"].endswith("Z")
