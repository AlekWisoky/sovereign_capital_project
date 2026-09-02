import json

from victor_ai_bot.omar.learning_quality import LearningQualityThresholds
from victor_ai_bot.omar.learning_quality_runtime import live_influence_quality
from victor_ai_bot.omar.real_learning import OmarRecommendation
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.omar.config import OmarConfig


def _write_events(path, *, complete=True):
    actions = ("WAIT", "DEFEND", "SEEK_OPP", "INCREASE_RISK", "DECREASE_RISK", "EXECUTE")
    with path.open("w", encoding="utf-8") as handle:
        for index in range(50):
            action = actions[index % len(actions)]
            correlation = f"corr-{index}" if complete else ""
            outcome = {
                "tx_hash": f"0x{index:064x}",
                "outcome_truth_verified": True,
                "metadata": {
                    "canonical_lineage": {
                        "decision_id": f"decision-{index}",
                        "correlation_id": correlation,
                    }
                },
            }
            handle.write(
                json.dumps(
                    {
                        "event": "omar_real_outcome",
                        "decision_id": f"decision-{index}",
                        "state_key": f"state-{index % 10}",
                        "action": action,
                        "reward": float(index) / 10.0,
                        "outcome": outcome,
                    }
                )
                + "\n"
            )


def test_runtime_learning_quality_requires_complete_lineage(tmp_path):
    runtime = OmarRuntime(OmarConfig(enabled=True), chain_name="quality")
    runtime._real_learner.path = str(tmp_path / "policy.json")
    _write_events(tmp_path / "policy.jsonl", complete=True)

    result = live_influence_quality(runtime)

    assert result["ready"] is True
    assert result["live_influence_allowed"] is True
    assert result["observations"] == 50
    assert result["unique_states"] == 10
    assert result["action_coverage"] == 1.0
    assert result["truth_rate"] == 1.0

    _write_events(tmp_path / "policy.jsonl", complete=False)
    blocked = live_influence_quality(runtime)
    assert blocked["ready"] is False
    assert "missing_lineage" in blocked["failures"]


def test_runtime_recommendation_is_blocked_until_quality_gate_passes(tmp_path, monkeypatch):
    runtime = OmarRuntime(OmarConfig(enabled=True), chain_name="recommend")
    runtime._real_learner.path = str(tmp_path / "policy.json")
    _write_events(tmp_path / "policy.jsonl", complete=False)

    trained = OmarRecommendation(
        state_key="state",
        action="EXECUTE",
        confidence=0.9,
        veto=False,
        size_mult=1.0,
        gas_mode="standard",
        trained=True,
        observations=100,
        reason="learned_execution_action",
    )
    monkeypatch.setattr(runtime._real_learner, "recommend", lambda context: trained)

    rec = runtime.recommend({"margin_ratio": 0.01})

    assert rec.action == "UNTRAINED"
    assert rec.trained is False
    assert rec.size_mult == 1.0
    assert rec.gas_mode == "standard"
    assert rec.reason.startswith("learning_quality_gate:")


def test_quality_thresholds_remain_explicit():
    thresholds = LearningQualityThresholds()
    assert thresholds.min_observations == 50
    assert thresholds.min_state_count == 10
    assert thresholds.max_missing_lineage_rate == 0.0
    assert thresholds.max_duplicate_rate == 0.0
