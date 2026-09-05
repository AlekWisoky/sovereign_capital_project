from __future__ import annotations

from victor_ai_bot.fund_os.health_states import HealthState
from victor_ai_bot.fund_os.launch_modes import LaunchMode, LaunchProfile
from victor_ai_bot.fund_os.staged_rollout import StagedRolloutManager
from victor_ai_bot.identity import new_decision_identity, new_execution_identity, new_settlement_identity
from victor_ai_bot.omar.operator_intent import OperatorIntentSnapshot
from victor_ai_bot.omar.real_learning import CapitalAuthoritySnapshot, OmarRealLearningLoop
from victor_ai_bot.omar.settled_ledger_bridge import ingest_settled_ledger_record


def test_runtime_method_chain_settlement_uses_canonical_lineage_for_learning(tmp_path):
    updates = []
    decision_identity = new_decision_identity()
    execution_identity = new_execution_identity(decision_identity)
    settlement_identity = new_settlement_identity(execution_identity)

    intent = OperatorIntentSnapshot(
        control_mode="auto",
        aggression_mode="aggressive",
        brain_mode="auto",
        risk_multiplier=0.75,
        desired_wealth_goal={"target_amount": "100000", "timeframe_days": 180},
        ai_recommendation={"action": "execute", "confidence": 0.92},
        source="runtime",
    )
    capital = CapitalAuthoritySnapshot(
        authority_id="prime-1",
        available_wei=5_000_000,
        allocatable_wei=2_000_000,
        family_allocatable_wei={"flash_arb": 1_500_000},
        status="healthy",
        freshness_class="fresh",
        reason_codes=[],
        source="capital_engine_state",
    )

    def policy_updater(attribution):
        updates.append(attribution)
        return {
            "ok": True,
            "learning_id": attribution.learning_id,
            "decision_id": attribution.decision_id,
            "action": attribution.action,
            "reward_wei": attribution.reward_wei,
        }

    loop = OmarRealLearningLoop(
        chain_name="ethereum",
        data_dir=str(tmp_path),
        policy_updater=policy_updater,
        capital_authority_reader=lambda: capital.to_dict(),
    )

    row = {
        "decision_id": decision_identity.decision_id,
        "correlation_id": decision_identity.correlation_id,
        "execution_id": execution_identity.execution_id,
        "outcome_id": "outcome-1",
        "sizing_id": "sizing-1",
        "settlement_id": settlement_identity.settlement_id,
        "transaction_id": "tx-1",
        "receipt_id": "0xabc",
        "action": "EXECUTE",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "policy_version": "policy-v1",
        "chain": "ethereum",
        "status": "settled",
        "metadata": {
            "decision_id": decision_identity.decision_id,
            "correlation_id": decision_identity.correlation_id,
            "execution_id": execution_identity.execution_id,
            "outcome_id": "outcome-1",
            "sizing_id": "sizing-1",
            "settlement_id": settlement_identity.settlement_id,
            "operator_intent": intent.to_dict(),
            "wealth_goal": {"target_amount": "100000", "timeframe_days": 180},
            "ai_recommendation": {"action": "execute", "confidence": 0.92},
            "capital_engine_state": capital.to_dict(),
            "execution": {
                "status": "confirmed",
                "fill_quantity": 1000,
                "fill_price": 1.25,
                "slippage_bps": 2.0,
                "gas_wei": 100,
            },
            "outcome": {
                "realized_after_gas_wei": 1000,
                "realized_gas_wei": 100,
                "realized_pnl_usd_micro": 4250000,
                "realized_slippage_bps": 2.0,
                "risk_cost_wei": 25,
            },
            "latency_ms": 37,
        },
    }

    result = ingest_settled_ledger_record(loop, row)

    assert result["ok"] is True
    assert result["eligible_for_learning"] is True
    assert result["lineage"]["decision_id"] == decision_identity.decision_id
    assert result["lineage"]["correlation_id"] == decision_identity.correlation_id
    assert result["lineage"]["execution_id"] == execution_identity.execution_id
    assert result["lineage"]["settlement_id"] == settlement_identity.settlement_id
    assert result["lineage"]["latency_class"] == "fast"

    decision = loop._decisions[decision_identity.decision_id]
    assert decision.operator_intent.aggression_mode == "aggressive"
    assert decision.operator_intent.desired_wealth_goal["target_amount"] == "100000"
    assert decision.operator_intent.ai_recommendation["action"] == "execute"
    assert decision.capital_authority.authority_id == "prime-1"
    assert decision.capital_authority.allocatable_wei == 2_000_000

    assert len(updates) == 1
    attribution = updates[0]
    assert attribution.decision_id == decision_identity.decision_id
    assert attribution.correlation_id == decision_identity.correlation_id
    assert attribution.execution_id == execution_identity.execution_id
    assert attribution.settlement_id == settlement_identity.settlement_id
    assert attribution.action == "EXECUTE"
    # realized_after_gas_wei is already net of gas; only risk_cost_wei remains
    # to be deducted from the learning reward.
    assert attribution.reward_wei == 975
    assert attribution.operator_intent.aggression_mode == "aggressive"
    assert attribution.operator_intent.desired_wealth_goal["timeframe_days"] == 180
    assert attribution.operator_intent.ai_recommendation["confidence"] == 0.92
    assert result["policy_update"]["ok"] is True


def test_v1_only_rollout_progresses_with_flash_arb_as_only_live_family():
    manager = object.__new__(StagedRolloutManager)
    manager.profile = LaunchProfile(mode=LaunchMode.V1_ONLY.value)

    manager._normalize_profile()

    assert manager.profile.active_families == ["flash_arb"]
    assert manager.profile.family_states["flash_arb"] == HealthState.LIVE.value
    assert all(
        state == HealthState.OBSERVE_ONLY.value
        for family, state in manager.profile.family_states.items()
        if family != "flash_arb"
    )
    assert manager.profile.exploration_budget["used_trades"] == 0
    assert manager.profile.exploration_budget["used_cost_usd"] == 0.0
