from types import SimpleNamespace

from victor_ai_bot.models import Opportunity, Route, RouteLeg
from victor_ai_bot.runtime_services.runtime_decision_finalize_facade import RuntimeDecisionFinalizeFacade


def test_canonical_decision_carries_capital_demand_from_authority():
    opp = Opportunity(
        id="opp-1",
        chain="ethereum",
        strategy="flash_arb",
        expected_profit_raw="100",
        expected_profit_usd="1",
        route=Route(
            legs=[
                RouteLeg(
                    dex="univ3",
                    venue="0x0000000000000000000000000000000000000001",
                    token_in="0x0000000000000000000000000000000000000002",
                    token_out="0x0000000000000000000000000000000000000003",
                    amount_in="1000",
                    min_out="1100",
                )
            ]
        ),
        min_outs=["1100"],
        route_id="route-1",
        meta={
            "strategy_family": "flashloan_atomic",
            "capital_source": "internal_prime",
            "goal_posture": {"risk_posture": "moderate", "target": "25%"},
        },
    )
    decision = SimpleNamespace(
        decision_id="decision-1",
        correlation_id="corr-1",
        opp_id="opp-1",
        route_id="route-1",
        size_mult=0.5,
        borrow_mult=1.0,
    )

    facade = RuntimeDecisionFinalizeFacade()
    facade.capital_engine_state = lambda: {
        "authority_id": "capital-authority-1",
        "capital_engine": {
            "deployable_bankroll_wei": 750,
            "family_allocations_wei": {"flashloan_atomic": 600},
        },
    }

    result = facade._attach_capital_demand(decision, opps=[opp])
    demand = result.capital_demand

    assert demand["schema_version"] == "capital_demand.v1"
    assert demand["decision_id"] == "decision-1"
    assert demand["correlation_id"] == "corr-1"
    assert demand["requested_capital_wei"] == "500"
    assert demand["authorized_capital_wei"] == "500"
    assert demand["authority_source"] == "capital_engine_state"
    assert demand["authority_id"] == "capital-authority-1"
    assert demand["capital_source"] == "internal_prime"
    assert demand["goal_posture"]["risk_posture"] == "moderate"
    assert demand["ultimately_deployed_capital_wei"] == "0"
    assert demand["authorization_status"] == "authorized"
