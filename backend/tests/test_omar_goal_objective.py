from __future__ import annotations

import inspect

import victor_ai_bot.omar.goal_objective as goal_objective
from victor_ai_bot.omar.goal_objective import (
    build_goal_objective_context,
    goal_advancement_reward,
    goal_state_bucket,
)


# Goal objective is a learning signal only; canonical execution/capital authority remains external.
def test_goal_context_uses_canonical_wealth_goal_state():
    context = build_goal_objective_context(
        {
            "state": {
                "targetReturnPct": 12.0,
                "currentReturnPct": 6.0,
                "progressPct": 50.0,
                "goalHorizonDays": 30,
                "goalHorizonCompatibility": 0.8,
                "goalUrgency": "catch_up",
                "pacing": "accelerate",
                "aggressivenessCap": 1.08,
                "goalAchieved": False,
                "goalStatus": "active",
            }
        }
    )
    assert context["goal_gap_pct"] == 6.0
    assert context["goal_gap_ratio"] == 0.5
    assert context["goal_horizon_compatibility"] == 0.8
    assert context["goal_urgency"] == "catch_up"
    assert "catch_up" in goal_state_bucket(context)


def test_goal_reward_is_bounded_and_cannot_turn_a_loss_into_profit():
    context = build_goal_objective_context(
        {
            "state": {
                "targetReturnPct": 12.0,
                "currentReturnPct": 2.0,
                "progressPct": 16.7,
                "goalHorizonCompatibility": 0.5,
                "goalUrgency": "catch_up",
                "pacing": "accelerate",
                "aggressivenessCap": 1.08,
            }
        }
    )
    reward = goal_advancement_reward(
        context=context,
        realized_net_usd=-10.0,
        expected_net_usd=5.0,
        amount_in_wei=10**18,
    )
    assert reward < 0.0
    assert -7.5 <= reward <= 7.5


def test_goal_reward_favors_positive_settled_progress_when_goal_has_gap():
    context = build_goal_objective_context(
        {
            "state": {
                "targetReturnPct": 12.0,
                "currentReturnPct": 3.0,
                "progressPct": 25.0,
                "goalHorizonCompatibility": 0.7,
                "goalUrgency": "catch_up",
                "pacing": "accelerate",
                "aggressivenessCap": 1.0,
            }
        }
    )
    reward = goal_advancement_reward(
        context=context,
        realized_net_usd=4.0,
        expected_net_usd=1.0,
        amount_in_wei=10**18,
    )
    assert reward > 0.0


def test_goal_objective_does_not_create_execution_or_capital_authority():
    source = inspect.getsource(goal_objective)
    assert "capital_engine_state" not in source
    assert "try_execute_opportunity" not in source
    assert "sign_transaction" not in source
