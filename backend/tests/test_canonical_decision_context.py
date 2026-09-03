import pytest

from victor_ai_bot.canonical_decision_context import (
    AIRecommendation,
    CanonicalDecisionContext,
    CapitalAuthority,
    HumanIntent,
    LatencyContext,
    WealthObjective,
    capital_authority_from_engine_state,
)


def test_context_carries_phase7_inputs_and_stable_lineage():
    ctx = CanonicalDecisionContext(
        decision_id="dec-001",
        correlation_id="corr-001",
        human_intent=HumanIntent(
            instruction="prioritize profitable opportunities",
            aggressiveness="aggressive",
            risk_multiplier=0.8,
        ),
        wealth_objective=WealthObjective(
            target_amount="1000000.000000000000000001",
            currency="usd",
            timeframe_seconds=86400,
        ),
        ai_recommendation=AIRecommendation(
            action="EXECUTE",
            rationale="positive after-cost EV",
            confidence=0.91,
            model="policy-v1",
        ),
        capital_authority=CapitalAuthority(
            deployable_bankroll_wei="123456789000000000000",
            internal_prime_wei="90000000000000000000",
            external_borrow_capacity_wei="5000000000000000000000",
            family_allocations_wei={"flashloan_atomic": "4000000000000000000000"},
            as_of_block=123,
        ),
        latency=LatencyContext(
            observed_at_ns=1000,
            market_data_age_ms=12.5,
            decision_latency_ms=3.2,
            execution_deadline_ms=800,
            gas_mode="fast",
        ),
        strategy_family="flashloan_atomic",
        opportunity_id="opp-1",
        route_id="route-1",
        created_at_ns=1000,
    )

    assert ctx.lineage() == {
        "decision_id": "dec-001",
        "correlation_id": "corr-001",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
    }
    assert ctx.wealth_objective.target_amount == "1000000.000000000000000001"
    assert ctx.capital_authority.external_borrow_capacity_wei == "5000000000000000000000"
    assert ctx.to_dict()["human_intent"]["aggressiveness"] == "aggressive"
    assert ctx.to_dict()["latency"]["execution_deadline_ms"] == 800


def test_capital_authority_uses_actual_capital_engine_snapshot():
    authority = capital_authority_from_engine_state(
        {
            "current_block": 777,
            "capital_engine": {
                "deployable_bankroll_wei": "100000000000000000000",
                "internal_prime_wei": "75000000000000000000",
                "external_borrow_capacity_wei": "2000000000000000000000",
                "family_allocations_wei": {"flashloan_atomic": "1500000000000000000000"},
                "authority_source": "capital_engine",
            },
        }
    )
    assert authority.deployable_bankroll_wei == "100000000000000000000"
    assert authority.internal_prime_wei == "75000000000000000000"
    assert authority.external_borrow_capacity_wei == "2000000000000000000000"
    assert authority.family_allocations_wei["flashloan_atomic"] == "1500000000000000000000"
    assert authority.as_of_block == 777


def test_context_requires_both_canonical_ids():
    with pytest.raises(ValueError, match="decision_id"):
        CanonicalDecisionContext(decision_id="", correlation_id="corr")
    with pytest.raises(ValueError, match="correlation_id"):
        CanonicalDecisionContext(decision_id="dec", correlation_id="")


def test_large_amounts_are_exact_and_nonfinite_amounts_rejected():
    authority = CapitalAuthority(
        deployable_bankroll_wei="999999999999999999999999999999999999",
        external_borrow_capacity_wei="1000000000000000000000000000000000000",
    )
    assert authority.deployable_bankroll_wei == "999999999999999999999999999999999999"
    with pytest.raises(ValueError, match="finite"):
        WealthObjective(target_amount="NaN")
