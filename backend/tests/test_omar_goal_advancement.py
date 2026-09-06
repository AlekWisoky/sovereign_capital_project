from victor_ai_bot.omar.goal_advancement import evaluate_goal_advancement


def _goal(**overrides):
    value = {
        "targetReturnPct": 10.0,
        "suggestedNextTargetPct": 12.0,
        "goalAchieved": True,
        "nextGoalAllowed": True,
        "stabilityScore": 0.85,
        "executionRealismScore": 0.82,
        "riskScore": 0.40,
        "goalHorizonCompatibility": 1.05,
    }
    value.update(overrides)
    return value


def _performance(**overrides):
    value = {
        "promotion_allowed": True,
        "observations": 60,
        "unique_states": 15,
        "mean_advantage_usd": 4.0,
        "lower_confidence_advantage_usd": 1.0,
    }
    value.update(overrides)
    return value


def test_goal_advancement_requires_verified_oos_performance():
    result = evaluate_goal_advancement(_goal(), _performance(promotion_allowed=False))
    assert result.allowed is False
    assert "performance_promotion_not_verified" in result.failures


def test_goal_advancement_requires_goal_completion():
    result = evaluate_goal_advancement(_goal(goalAchieved=False), _performance())
    assert result.allowed is False
    assert "active_goal_not_achieved" in result.failures


def test_goal_advancement_requires_positive_oos_confidence_bound():
    result = evaluate_goal_advancement(
        _goal(), _performance(lower_confidence_advantage_usd=-0.01)
    )
    assert result.allowed is False
    assert "oos_confidence_bound_not_positive" in result.failures


def test_goal_advancement_accepts_healthy_completed_goal_and_oos_edge():
    result = evaluate_goal_advancement(_goal(), _performance())
    assert result.allowed is True
    assert result.reason == "goal_advancement_verified"
    assert result.current_target_pct == 10.0
    assert result.next_target_pct == 12.0
