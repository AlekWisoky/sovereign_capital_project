from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_economics import (
    build_decision_economic_context,
    expectation_error,
)
from victor_ai_bot.runtime_services.runtime_decision_finalize_facade import (
    RuntimeDecisionFinalizeFacade,
)
from victor_ai_bot.runtime_services.runtime_execute_wrapper_facade import (
    RuntimeExecuteWrapperFacade,
)


def _opp():
    return SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        expected_profit_raw="1234",
        meta={
            "profitability": {
                "profit_after_costs_wei": "9000",
                "gas_cost_wei": "1000",
                "expected_profit_after_gas_usd_micro": 4200000,
            },
            "capture": {
                "metadata": {
                    "endpoint_selection": {"measured_latency_ms": 140.0},
                    "telemetry": {"lane_avg_latency_ms": 160.0},
                }
            },
        },
    )


def test_decision_economic_context_uses_authoritative_profit_and_capture_latency():
    cfg = SimpleNamespace(execution=SimpleNamespace(deadline_seconds=30))
    ctx = build_decision_economic_context(_opp(), cfg=cfg)

    assert ctx.expected_profit_after_costs_wei == 9000
    assert ctx.expected_profit_after_costs_usd_micro == 4200000
    assert ctx.expected_gas_cost_wei == 1000
    assert ctx.expected_latency_ms == 140.0
    assert ctx.delivery_budget_ms == 30000.0
    assert ctx.delivery_headroom_ms == 29860.0


def test_decision_finalize_attaches_frozen_economic_context():
    facade = object.__new__(RuntimeDecisionFinalizeFacade)
    facade.cfg = SimpleNamespace(execution=SimpleNamespace(deadline_seconds=30))
    decision = SimpleNamespace(opp_id="opp-1", metadata={})
    opp = _opp()

    facade._attach_decision_economic_context(decision, opps=[opp])

    economic = decision.metadata["economic_context"]
    assert economic["expected_profit_after_costs_wei"] == 9000
    assert economic["expected_latency_ms"] == 140.0
    assert economic["delivery_budget_ms"] == 30000.0
    assert opp.meta["decision_economic_context"] == economic


def test_execution_boundary_copies_economics_to_plan_and_brain():
    decision = SimpleNamespace(
        metadata={
            "economic_context": {
                "expected_profit_after_costs_wei": 9000,
                "expected_latency_ms": 140.0,
                "delivery_budget_ms": 30000.0,
            }
        }
    )
    opp = _opp()
    result = SimpleNamespace(plan={}, ok=True)

    RuntimeExecuteWrapperFacade._propagate_decision_economics(result, decision, opp)

    assert result.plan["economic_context"]["expected_profit_after_costs_wei"] == 9000
    assert result.plan["decision_context"]["economic_context"]["expected_latency_ms"] == 140.0
    assert opp.meta["brain"]["economic_context"]["delivery_budget_ms"] == 30000.0


def test_expectation_error_is_signed_realized_minus_expected():
    error = expectation_error(
        expected_profit_after_costs_wei=1000,
        realized_net_wei=750,
        expected_latency_ms=100.0,
        realized_latency_ms=180.0,
    )

    assert error["net_error_wei"] == "-250"
    assert error["net_error_pct"] == -25.0
    assert error["latency_error_ms"] == 80.0
