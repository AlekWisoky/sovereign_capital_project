from dataclasses import dataclass

from victor_ai_bot.identity import (
    new_decision_identity,
    new_execution_identity,
    new_settlement_identity,
)
from victor_ai_bot.omar.operator_intent import OperatorIntentSnapshot, capture_operator_intent
from victor_ai_bot.omar.real_learning import OmarRealLearningLoop


@dataclass
class Controls:
    control_mode: str = "auto"
    aggression_mode: str = "aggressive"
    brain_mode: str = "rl"
    force_send_mode: str = "protected_rpc"
    force_gas_mode: str = "fast"


class WealthGoal:
    def state(self, runtime):
        return {
            "goal": {
                "target_return_percentage": 25.0,
                "time_horizon_seconds": 30 * 24 * 3600,
                "risk_tolerance": "aggressive",
            },
            "posture": {"aggressiveness_cap": 1.05},
        }


class Runtime:
    _cc = type("CC", (), {"controls": Controls()})()
    _wealth_goal_service = WealthGoal()


def test_operator_intent_snapshot_captures_human_goal_and_recommendation():
    decision = type(
        "Decision",
        (),
        {
            "action": "trade",
            "opp_id": "opp-1",
            "route_id": "route-1",
            "size_mult": 0.75,
            "borrow_mult": 1.0,
            "gas_mode": "fast",
            "p_success": 0.91,
            "ev_wei": 123,
            "reason": "candidate",
            "rl_state": "tight_margin",
            "rl_action_index": 2,
        },
    )()

    intent = capture_operator_intent(Runtime(), decision)

    assert intent.control_mode == "auto"
    assert intent.aggression_mode == "aggressive"
    assert intent.brain_mode == "rl"
    assert intent.force_send_mode == "protected_rpc"
    assert intent.force_gas_mode == "fast"
    assert intent.desired_wealth_goal["goal"]["target_return_percentage"] == 25.0
    assert intent.desired_wealth_goal["goal"]["time_horizon_seconds"] == 30 * 24 * 3600
    assert intent.ai_recommendation["action"] == "trade"
    assert intent.ai_recommendation["opp_id"] == "opp-1"
    assert intent.ai_recommendation["p_success"] == 0.91


def test_operator_intent_is_propagated_decision_to_execution_to_settlement(tmp_path):
    intent = OperatorIntentSnapshot(
        control_mode="auto",
        aggression_mode="aggressive",
        brain_mode="rl",
        risk_multiplier=0.85,
        force_send_mode="protected_rpc",
        force_gas_mode="fast",
        desired_wealth_goal={
            "target_amount_usd": 10000.0,
            "time_horizon_seconds": 14 * 24 * 3600,
        },
        ai_recommendation={"action": "trade", "p_success": 0.88},
    )
    identity = new_decision_identity()
    execution_identity = new_execution_identity(identity)
    settlement_identity = new_settlement_identity(execution_identity)

    loop = OmarRealLearningLoop(data_dir=str(tmp_path))
    loop.record_decision(
        decision_id=identity.decision_id,
        correlation_id=identity.correlation_id,
        action="trade",
        operator_intent=intent,
    )
    execution = loop.bind_execution(
        decision_id=execution_identity.decision_id,
        correlation_id=execution_identity.correlation_id,
        execution_id=execution_identity.execution_id,
        status="filled",
        action="trade",
    )
    attribution = loop.settle_outcome(
        decision_id=settlement_identity.decision_id,
        correlation_id=settlement_identity.correlation_id,
        execution_id=settlement_identity.execution_id,
        settlement_id=settlement_identity.settlement_id,
        status="settled",
        realized_pnl_wei=100,
        realized_gas_wei=10,
    )

    assert execution.operator_intent == intent
    assert attribution.operator_intent == intent
    assert attribution.reward_wei == 90
    assert attribution.eligible_for_learning is True

    events = [
        line
        for line in (tmp_path / "omar_real_learning_default.jsonl").read_text().splitlines()
        if line
    ]
    assert len(events) == 4
    assert all('"operator_intent"' in event for event in events)
