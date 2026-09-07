from victor_ai_bot.runtime_services.omar_human_context import (
    OmarHumanContext,
    learning_features,
    normalize_human_context,
)


def test_normalize_human_context_bounds_human_intent():
    ctx = normalize_human_context(
        {
            "aggressiveness_mode": "AGGRESSIVE",
            "desired_wealth_goal_amount": "100000",
            "desired_wealth_goal_timeframe_days": "365",
            "ai_recommendation_id": "rec-123",
            "ai_recommendation_source": "advisor",
        }
    )
    assert ctx == OmarHumanContext(
        aggressiveness_mode="aggressive",
        desired_wealth_goal_amount=100000.0,
        desired_wealth_goal_timeframe_days=365,
        ai_recommendation_id="rec-123",
        ai_recommendation_source="advisor",
    )


def test_invalid_human_intent_falls_back_without_breaking_hot_path():
    ctx = normalize_human_context(
        {
            "aggressiveness_mode": "reckless",
            "desired_wealth_goal_amount": "bad",
            "desired_wealth_goal_timeframe_days": 0,
        }
    )
    assert ctx.aggressiveness_mode == "balanced"
    assert ctx.desired_wealth_goal_amount is None
    assert ctx.desired_wealth_goal_timeframe_days is None


def test_learning_features_do_not_include_identity_fields():
    ctx = normalize_human_context(
        {
            "aggressiveness_mode": "conservative",
            "desired_wealth_goal_amount": 1000,
            "desired_wealth_goal_timeframe_days": 100,
            "ai_recommendation_id": "rec-secret-lineage",
        }
    )
    features = learning_features(ctx, current_wealth=750)
    assert features["human_aggressiveness"] == -1.0
    assert features["wealth_goal_progress"] == -0.25
    assert "ai_recommendation_id" not in features
    assert "correlation_id" not in features
    assert "decision_id" not in features
