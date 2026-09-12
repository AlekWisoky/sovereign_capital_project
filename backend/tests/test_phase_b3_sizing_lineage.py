from types import SimpleNamespace

from victor_ai_bot.execution_capture.institutional_sizing import (
    CapitalAuthoritySizingContext,
    EconomicsSizingContext,
    ExecutionSizingContext,
    GovernanceSizingContext,
    InstitutionalSizingContract,
    LiquiditySizingContext,
    SettlementSizingContext,
    WealthGoalSizingContext,
)
from victor_ai_bot.runtime_services.capital_admission_service import (
    CapitalAdmissionService,
    PreTradeCapitalAdmission,
)
from victor_ai_bot.runtime_services.institutional_sizing_runtime import (
    InstitutionalSizingAdmissionService,
)


def _contract():
    return InstitutionalSizingContract(
        contract_version="institutional_sizing_v1",
        strategy_family="flash_arb",
        capital_source="internal_prime",
        requested_notional_usd=1_000_000.0,
        target_notional_usd=1_000_000.0,
        base_borrow_amount_wei=0,
        max_borrow_amount_wei=0,
        liquidity=LiquiditySizingContext(
            available_usd=2_000_000.0,
            depth_usd=1_500_000.0,
            pool_depth_cap_usd=1_200_000.0,
            provider_capacity_usd=1_500_000.0,
            route_capacity_usd=1_400_000.0,
        ),
        execution=ExecutionSizingContext(
            expected_pipeline_latency_ms=250.0,
            latency_half_life_ms=1_200.0,
            latency_pressure=0.15,
            endpoint_quality=0.90,
            venue_reliability=0.90,
            simulation_confidence=0.92,
            freshness_score=0.95,
        ),
        economics=EconomicsSizingContext(
            expected_gross_profit_usd=1_500.0,
            expected_net_profit_usd=1_000.0,
            gas_cost_usd=100.0,
            borrow_cost_usd=100.0,
            slippage_cost_usd=200.0,
            latency_cost_usd=50.0,
            failure_cost_usd=150.0,
            min_profit_usd=50.0,
            min_profit_bps=2.0,
            success_probability=0.92,
            margin_ratio=0.01,
        ),
        capital=CapitalAuthoritySizingContext(
            status="ok",
            freshness="fresh",
            authority_id="cap-auth-1",
            deployable_usd=2_000_000.0,
            drawdown_buffer_usd=900_000.0,
            prime_available=True,
            prime_capacity_usd=10_000_000.0,
            prime_utilization=0.10,
            prime_reserved_usd=0.0,
            prime_family_exposure_usd=0.0,
            family_cap_usd=5_000_000.0,
        ),
        wealth_goal=WealthGoalSizingContext(
            capital_commitment_pct=30.0,
            aggressiveness_cap=1.0,
            max_drawdown_pct=10.0,
            drawdown_pct=1.0,
        ),
        governance=GovernanceSizingContext(
            admitted=True,
            reason_code="ok",
            strategy_family="flash_arb",
            capital_source="internal_prime",
            live_authority=False,
            execution_allowed=True,
            max_deployable_pct=0.35,
        ),
        settlement=SettlementSizingContext(),
    )


def test_phase_b3_calculates_and_attaches_sizing_identity(monkeypatch):
    contract = _contract()
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.institutional_sizing_runtime.build_institutional_sizing_contract",
        lambda **_: contract,
    )
    monkeypatch.setattr(
        CapitalAdmissionService,
        "evaluate",
        lambda self, runtime, opp, decision=None: PreTradeCapitalAdmission(
            allowed=True,
            reason_code="ok",
            strategy_family="flash_arb",
            capital_source="internal_prime",
            requested_notional_usd=1_000_000.0,
            projected_realized_edge_usd=1_000.0,
            confidence=0.92,
            details={},
        ),
    )

    runtime = SimpleNamespace(
        capital_engine_state=lambda: {
            "status": "ok",
            "freshness_class": "fresh",
            "authority_id": "cap-auth-1",
            "deployable_usd": 2_000_000.0,
            "internal_prime_available": True,
            "family_caps_usd": {"flash_arb": 5_000_000.0},
        },
        _internal_prime=SimpleNamespace(
            state=lambda: {
                "stateReady": True,
                "capacityUsd": 10_000_000.0,
                "utilization": 0.10,
                "reservedCollateralUsd": 0.0,
                "familyExposure": {"flash_arb": 0.0},
            }
        ),
        _wealth_goal_service=SimpleNamespace(state=lambda: {}),
        cfg=SimpleNamespace(execution=SimpleNamespace(live_authority=False)),
    )
    opp = SimpleNamespace(meta={"capture": {"metadata": {}}})
    decision = SimpleNamespace(metadata={})

    result = InstitutionalSizingAdmissionService().evaluate(runtime, opp, decision=decision)
    record = result.details["institutionalSizing"]
    sizing_id = record["sizing"]["sizing_id"]

    assert result.allowed is True
    assert record["valid"] is True
    assert sizing_id.startswith("size-")
    assert opp.meta["sizing_id"] == sizing_id
    assert opp.meta["canonical_lineage"]["sizing_id"] == sizing_id
    assert decision.metadata["sizing_id"] == sizing_id
    assert record["sizing"]["approved_notional_usd"] <= 1_000_000.0
