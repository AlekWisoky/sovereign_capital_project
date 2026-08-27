from __future__ import annotations

from victor_ai_bot.omar.learning_quality import (
    LearningQualityThresholds,
    evaluate_learning_quality,
)


def _event(i: int, *, action: str = "EXECUTE", truth: bool = True) -> dict:
    return {
        "decision_id": f"decision-{i}",
        "correlation_id": f"corr-{i}",
        "state_key": f"state-{i}",
        "action": action,
        "reward": float(i % 3 - 1),
        "outcome_truth_verified": truth,
    }


def test_learning_quality_accepts_sufficient_diverse_verified_data():
    actions = ["WAIT", "DEFEND", "SEEK_OPP", "INCREASE_RISK", "DECREASE_RISK", "EXECUTE"]
    events = [
        _event(i, action=actions[i % len(actions)])
        for i in range(60)
    ]
    result = evaluate_learning_quality(
        events,
        LearningQualityThresholds(min_observations=50, min_state_count=10),
    )
    assert result.ready is True
    assert result.reason == "quality_verified"
    assert result.truth_rate == 1.0
    assert result.invalid_reward_count == 0


def test_learning_quality_rejects_insufficient_or_low_quality_data():
    events = [_event(i) for i in range(10)]
    result = evaluate_learning_quality(
        events,
        LearningQualityThresholds(min_observations=20, min_state_count=5),
    )
    assert result.ready is False
    assert "insufficient_observations" in result.failures

    events = [_event(i, truth=(i != 0)) for i in range(20)]
    result = evaluate_learning_quality(
        events,
        LearningQualityThresholds(min_observations=20, min_state_count=5, min_truth_rate=1.0),
    )
    assert result.ready is False
    assert "insufficient_truth_verification" in result.failures


def test_learning_quality_rejects_duplicate_identity_and_missing_lineage():
    events = [_event(i) for i in range(20)]
    events[1]["decision_id"] = events[0]["decision_id"]
    result = evaluate_learning_quality(
        events,
        LearningQualityThresholds(min_observations=20, min_state_count=5),
    )
    assert result.ready is False
    assert "duplicate_learning_identity" in result.failures

    events[2]["correlation_id"] = ""
    result = evaluate_learning_quality(
        events,
        LearningQualityThresholds(min_observations=20, min_state_count=5),
    )
    assert "missing_lineage" in result.failures


def test_learning_quality_does_not_treat_positive_reward_as_promotion():
    events = [_event(i) for i in range(60)]
    for row in events:
        row["reward"] = 100.0
    result = evaluate_learning_quality(
        events,
        LearningQualityThresholds(min_observations=50, min_state_count=10),
    )
    assert result.ready is True
    assert result.reason == "quality_verified"
    # Profitability/policy superiority is intentionally a separate gate.
