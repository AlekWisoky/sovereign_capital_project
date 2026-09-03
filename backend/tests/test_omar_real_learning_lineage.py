from __future__ import annotations

from victor_ai_bot.omar.operator_intent import OperatorIntentSnapshot
from victor_ai_bot.omar.real_learning import OmarRealLearningLoop


def test_real_learning_preserves_complete_canonical_lineage_and_action_attribution(
    tmp_path,
):
    updates = []

    def update_policy(attribution):
        updates.append(attribution)
        return {"updated": True, "learning_id": attribution.learning_id}

    loop = OmarRealLearningLoop(
        chain_name="ethereum",
        data_dir=str(tmp_path),
        policy_updater=update_policy,
        capital_authority_reader=lambda: {
            "authority_id": "capital-authority-1",
            "available_wei": 10_000,
            "allocatable_wei": 7_500,
            "family_allocatable_wei": {"flash_arb": 5_000},
            "status": "authorized",
            "freshness_class": "fresh",
            "source": "capital_engine_state",
        },
    )
    intent = OperatorIntentSnapshot(
        control_mode="operator",
        aggression_mode="aggressive",
        brain_mode="auto",
        risk_multiplier=0.75,
        desired_wealth_goal={"target_amount": "100000", "timeframe_days": 180},
        ai_recommendation={"action": "execute", "confidence": 0.92},
    )

    decision = loop.record_decision(
        decision_id="decision-1",
        correlation_id="corr-1",
        action="EXECUTE",
        opp_id="opp-1",
        route_id="route-1",
        policy_version="policy-v1",
        state={"rl_state": "state-1"},
        operator_intent=intent,
    )
    assert decision.decision_id == "decision-1"
    assert decision.correlation_id == "corr-1"
    assert decision.capital_authority.source == "capital_engine_state"
    assert decision.operator_intent.aggression_mode == "aggressive"

    execution = loop.bind_execution(
        decision_id="decision-1",
        correlation_id="corr-1",
        execution_id="execution-1",
        status="submitted",
        action="EXECUTE",
        tx_hash="0xabc",
        fill_quantity=2.0,
        fill_price=100.0,
        slippage_bps=2.0,
        gas_wei=100,
        latency_ms=37.0,
    )
    assert execution.decision_id == decision.decision_id
    assert execution.correlation_id == decision.correlation_id
    assert execution.execution_id == "execution-1"
    assert execution.operator_intent == intent

    attribution = loop.settle_outcome(
        decision_id="decision-1",
        correlation_id="corr-1",
        execution_id="execution-1",
        settlement_id="settlement-1",
        status="settled",
        realized_pnl_wei=1_000,
        realized_pnl_usd_micro=4_250_000,
        realized_slippage_bps=2.0,
        realized_gas_wei=100,
        risk_cost_wei=50,
        metadata={"truth_verified": True, "latency_ms": 37},
    )

    assert attribution.eligible_for_learning is True
    assert attribution.decision_id == "decision-1"
    assert attribution.correlation_id == "corr-1"
    assert attribution.execution_id == "execution-1"
    assert attribution.settlement_id == "settlement-1"
    assert attribution.action == "EXECUTE"
    assert attribution.reward_wei == 850
    assert attribution.operator_intent == intent
    assert len(updates) == 1
    assert updates[0].learning_id == attribution.learning_id


def test_real_learning_does_not_update_policy_from_unsettled_outcome(tmp_path):
    updates = []

    loop = OmarRealLearningLoop(
        chain_name="ethereum",
        data_dir=str(tmp_path),
        policy_updater=lambda attribution: updates.append(attribution) or {"updated": True},
    )
    loop.record_decision(
        decision_id="decision-2",
        correlation_id="corr-2",
        action="EXECUTE",
        opp_id="opp-2",
        route_id="route-2",
    )
    loop.bind_execution(
        decision_id="decision-2",
        correlation_id="corr-2",
        execution_id="execution-2",
        status="submitted",
        action="EXECUTE",
        tx_hash="0xpending",
    )

    attribution = loop.settle_outcome(
        decision_id="decision-2",
        correlation_id="corr-2",
        execution_id="execution-2",
        settlement_id="settlement-pending",
        status="pending",
        realized_pnl_wei=1_000,
    )

    assert attribution.eligible_for_learning is False
    assert attribution.reason_codes == ["outcome_not_settled"]
    assert updates == []
