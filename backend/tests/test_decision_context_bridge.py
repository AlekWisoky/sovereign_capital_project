from dataclasses import dataclass, field

from victor_ai_bot.decision_context_bridge import (
    build_decision_context,
    execution_record,
    learning_record,
    settled_outcome_record,
)


@dataclass
class Opportunity:
    id: str = "opp-42"
    route_id: str = "route-42"
    meta: dict = field(default_factory=lambda: {
        "strategy_family": "flashloan_atomic",
        "human_intent": {
            "instruction": "grow treasury while preserving capital safety",
            "aggressiveness": "aggressive",
            "risk_multiplier": 0.9,
        },
        "wealth_objective": {
            "target_amount": "2500000",
            "currency": "USD",
            "timeframe_seconds": 2592000,
        },
        "brain": {
            "action": "EXECUTE",
            "p_success": 0.93,
            "reason": "positive_after_costs_ev",
            "model": "UNIFIED_ROLE_POLICY_V1",
            "gas_mode": "fast",
        },
        "latency": {
            "market_data_age_ms": 8.5,
            "decision_latency_ms": 2.1,
            "execution_deadline_ms": 750,
        },
    })


def test_context_is_created_once_and_reused_by_execution_outcome_learning():
    context = build_decision_context(
        opportunity=Opportunity(),
        current_block=900,
        capital_engine_state={
            "current_block": 900,
            "capital_engine": {
                "deployable_bankroll_wei": "100000000000000000000",
                "internal_prime_wei": "90000000000000000000",
                "external_borrow_capacity_wei": "5000000000000000000000",
                "family_allocations_wei": {"flashloan_atomic": "5000000000000000000000"},
            },
        },
        decision_id="dec-prod-1",
        correlation_id="corr-prod-1",
    )

    execution = execution_record(context, execution_id="exec-1", status="submitted", tx_hash="0xabc")
    outcome = settled_outcome_record(
        context,
        outcome_id="out-1",
        status="settled",
        tx_hash="0xabc",
        realized_after_gas_wei="123000000000000000",
        slippage_wei="1200000000000",
    )
    learning = learning_record(context, outcome_id="out-1", reward="123000000000000000")

    for record in (execution, outcome, learning):
        assert record["decision_id"] == "dec-prod-1"
        assert record["correlation_id"] == "corr-prod-1"
        assert record["opportunity_id"] == "opp-42"
        assert record["route_id"] == "route-42"
        assert record["decision_context"]["capital_authority"]["external_borrow_capacity_wei"] == "5000000000000000000000"
        assert record["decision_context"]["wealth_objective"]["target_amount"] == "2500000"
        assert record["decision_context"]["human_intent"]["aggressiveness"] == "aggressive"
        assert record["decision_context"]["latency"]["market_data_age_ms"] == 8.5
