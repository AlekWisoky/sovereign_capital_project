import json

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.performance_promotion import (
    PerformancePromotionThresholds,
    evaluate_performance_promotion,
)
from victor_ai_bot.omar.performance_promotion_runtime import (
    live_performance_promotion,
)
from victor_ai_bot.omar.real_learning import OmarRecommendation
from victor_ai_bot.omar.runtime import OmarRuntime


def _write_oos(path, *, advantage=True, count=50):
    with path.open("w", encoding="utf-8") as handle:
        for index in range(count):
            baseline = 10.0
            candidate = 10.10 if advantage else 9.90
            handle.write(
                json.dumps(
                    {
                        "event": "omar_policy_oos_evaluation",
                        "evaluation_split": "out_of_sample",
                        "evaluation_id": f"eval-{index}",
                        "decision_id": f"decision-oos-{index}",
                        "state_key": f"state-{index % 10}",
                        "candidate_reward_usd": candidate,
                        "baseline_reward_usd": baseline,
                    }
                )
                + "\n"
            )


def test_performance_promotion_requires_oos_advantage():
    result = evaluate_performance_promotion(
        [
            {
                "evaluation_split": "out_of_sample",
                "state_key": f"state-{i % 10}",
                "candidate_reward_usd": 10.10,
                "baseline_reward_usd": 10.0,
            }
            for i in range(50)
        ],
        thresholds=PerformancePromotionThresholds(min_mean_advantage_bps=5.0),
    )
    assert result.ready is True
    assert result.reason == "performance_verified"
    assert result.mean_advantage_usd == 0.1
    assert result.win_rate == 1.0


def test_performance_promotion_blocks_when_candidate_loses():
    result = evaluate_performance_promotion(
        [
            {
                "evaluation_split": "out_of_sample",
                "state_key": f"state-{i % 10}",
                "candidate_reward_usd": 9.90,
                "baseline_reward_usd": 10.0,
            }
            for i in range(50)
        ]
    )
    assert result.ready is False
    assert "insufficient_mean_advantage" in result.failures
    assert "insufficient_win_rate" in result.failures


def test_live_performance_promotion_reads_runtime_event_stream(tmp_path):
    runtime = OmarRuntime(OmarConfig(enabled=True), chain_name="oos")
    runtime._real_learner.path = str(tmp_path / "real_policy.json")
    path = tmp_path / "performance_oos.jsonl"
    _write_oos(path)

    result = live_performance_promotion(runtime)

    assert result["promotion_allowed"] is True
    assert result["observations"] == 50
    assert result["unique_states"] == 10


def test_runtime_recommendation_requires_both_gates(tmp_path, monkeypatch):
    runtime = OmarRuntime(OmarConfig(enabled=True), chain_name="combined")
    runtime._real_learner.path = str(tmp_path / "real_policy.json")

    quality_path = tmp_path / "real_policy.jsonl"
    with quality_path.open("w", encoding="utf-8") as handle:
        for index in range(50):
            handle.write(
                json.dumps(
                    {
                        "event": "omar_real_outcome",
                        "decision_id": f"decision-{index}",
                        "correlation_id": f"corr-{index}",
                        "state_key": f"state-{index % 10}",
                        "action": "EXECUTE",
                        "reward": 1.0,
                        "outcome": {
                            "tx_hash": f"0x{index:064x}",
                            "outcome_truth_verified": True,
                        },
                    }
                )
                + "\n"
            )

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

    blocked = runtime.recommend({"margin_ratio": 0.01})
    assert blocked.action == "UNTRAINED"
    assert blocked.reason.startswith("performance_promotion_gate:")

    _write_oos(tmp_path / "performance_combined.jsonl")
    promoted = runtime.recommend({"margin_ratio": 0.01})
    assert promoted.action == "EXECUTE"
    assert promoted.trained is True
