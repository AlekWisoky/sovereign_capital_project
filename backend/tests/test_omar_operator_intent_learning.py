from __future__ import annotations

from victor_ai_bot.omar.real_learning import OmarRealLearner


def _context(**overrides):
    value = {
        "margin_ratio": 0.0012,
        "gas_ratio": 0.0003,
        "p_success": 0.82,
        "drawdown_pct": 2.0,
        "execution_realism": 0.8,
        "stability": 0.8,
        "goal_gap_pct": 3.0,
        "goal_horizon_compatibility": 0.9,
        "volatility": 0.12,
        "legs": 2,
        "capital_source": "internal_prime",
        "internal_prime_available": True,
        "prime_capacity_ratio": 0.8,
        "prime_cost_bps": 3.0,
        "aggression_mode": "balanced",
        "risk_multiplier": 1.0,
        "ai_recommendation_action": "none",
        "ai_recommendation_posture": "none",
        "ai_recommendation_confidence": 0.0,
    }
    value.update(overrides)
    return value


def test_operator_intent_changes_learning_state_without_raw_ids():
    base = OmarRealLearner.state_key(_context())
    aggressive = OmarRealLearner.state_key(_context(aggression_mode="aggressive"))
    defensive = OmarRealLearner.state_key(
        _context(
            aggression_mode="conservative",
            risk_multiplier=0.6,
            ai_recommendation_action="reduce_exposure",
            ai_recommendation_posture="defensive",
            ai_recommendation_confidence=0.91,
        )
    )

    assert base != aggressive
    assert aggressive != defensive
    assert "corr-" not in defensive
    assert "prime-123" not in defensive


def test_goal_horizon_and_ai_confidence_are_bucketed():
    behind = OmarRealLearner.state_key(_context(goal_horizon_compatibility=0.45))
    on_track = OmarRealLearner.state_key(_context(goal_horizon_compatibility=1.05))
    high_confidence = OmarRealLearner.state_key(
        _context(ai_recommendation_action="execute", ai_recommendation_confidence=0.95)
    )

    assert behind != on_track
    assert on_track != high_confidence
