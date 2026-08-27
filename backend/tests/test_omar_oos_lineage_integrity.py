from __future__ import annotations

import json

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.oos_evidence import oos_evidence_path
from victor_ai_bot.omar.oos_lineage_integrity import filter_integrity_valid_oos_rows, validate_oos_lineage
from victor_ai_bot.omar.performance_promotion import PerformancePromotionThresholds
from victor_ai_bot.omar.performance_promotion_runtime import live_performance_promotion, performance_promotion
from victor_ai_bot.omar.runtime import OmarRuntime


def _runtime(tmp_path):
    import os

    os.environ["VICTOR_DATA_DIR"] = str(tmp_path)
    return OmarRuntime(OmarConfig(enabled=True, real_learning_min_observations=1), chain_name="test")


def test_oos_lineage_integrity_requires_decision_correlation_execution_and_outcome():
    good = {
        "event": "omar_oos_evidence",
        "evaluation_split": "out_of_sample",
        "decision_id": "dec-1",
        "correlation_id": "corr-1",
        "execution_id": "exec-1",
        "outcome_id": "out-1",
        "state_key": "state-1",
        "action": "EXECUTE",
        "candidate_reward_usd": 2.0,
        "baseline_reward_usd": 1.0,
    }
    assert validate_oos_lineage(good) == (True, ())
    bad = dict(good)
    bad.pop("execution_id")
    ok, missing = validate_oos_lineage(bad)
    assert ok is False
    assert "execution_id" in missing


def test_performance_promotion_excludes_incomplete_oos_lineage(tmp_path):
    rt = _runtime(tmp_path)
    path = oos_evidence_path(rt)
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = [
        {
            "event": "omar_oos_evidence",
            "evaluation_split": "out_of_sample",
            "decision_id": "dec-good",
            "correlation_id": "corr-good",
            "execution_id": "exec-good",
            "outcome_id": "out-good",
            "state_key": "state-good",
            "action": "EXECUTE",
            "candidate_reward_usd": 2.0,
            "baseline_reward_usd": 1.0,
        },
        {
            "event": "omar_oos_evidence",
            "evaluation_split": "out_of_sample",
            "decision_id": "dec-bad",
            "correlation_id": "corr-bad",
            "state_key": "state-bad",
            "action": "EXECUTE",
            "candidate_reward_usd": 100.0,
            "baseline_reward_usd": 1.0,
        },
    ]
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    result = performance_promotion(
        rt,
        thresholds=PerformancePromotionThresholds(
            min_evaluation_observations=1,
            min_unique_states=1,
            min_mean_advantage_usd=0.5,
            min_mean_advantage_bps=1000.0,
            min_win_rate=1.0,
            min_lower_confidence_advantage_usd=-100.0,
        ),
    )
    assert result.observations == 1
    assert result.candidate_reward_usd == 2.0
    assert result.baseline_reward_usd == 1.0

    live = live_performance_promotion(rt)
    assert live["promotion_allowed"] is False
    assert live["oos_lineage_integrity"]["rejected_rows"] == 1
    assert live["oos_lineage_integrity"]["missing_execution_id"] == 1
    assert live["reason"] == "incomplete_oos_lineage"


def test_complete_oos_lineage_can_promote_when_performance_thresholds_pass(tmp_path):
    rt = _runtime(tmp_path)
    path = oos_evidence_path(rt)
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    for i in range(2):
        row = {
            "event": "omar_oos_evidence",
            "evaluation_split": "out_of_sample",
            "decision_id": f"dec-{i}",
            "correlation_id": f"corr-{i}",
            "execution_id": f"exec-{i}",
            "outcome_id": f"out-{i}",
            "state_key": f"state-{i}",
            "action": "EXECUTE",
            "candidate_reward_usd": 2.0,
            "baseline_reward_usd": 1.0,
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    rows, integrity = filter_integrity_valid_oos_rows(json.loads(line) for line in open(path, encoding="utf-8"))
    assert len(rows) == 2
    assert integrity.ready is True
    assert integrity.coverage == 1.0
