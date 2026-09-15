from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.calldata_builder import build_execute_calldata
from victor_ai_bot.execution_capture.flashloan_hardening import evaluate_flashloan_resilience
from victor_ai_bot.execution_capture.institutional_sizing import (
    CapitalAuthoritySizingContext,
    EconomicsSizingContext,
    ExecutionSizingContext,
    GovernanceSizingContext,
    InstitutionalSizingContract,
    LiquiditySizingContext,
    SettlementSizingContext,
    WealthGoalSizingContext,
    INSTITUTIONAL_V1_TIERS,
)
from victor_ai_bot.execution_capture.institutional_sizing_kernel import calculate_institutional_size
from victor_ai_bot.execution_capture.models import OpportunityEnvelope, SafeSizePoint


ASSET = "0x1111111111111111111111111111111111111111"
USDC = "0x2222222222222222222222222222222222222222"
VENUE = "0x3333333333333333333333333333333333333333"
PROFIT_TO = "0x0000000000000000000000000000000000000001"


def _legs() -> list[dict[str, object]]:
    return [
        {
            "dex": "univ3",
            "venue": VENUE,
            "token_in": ASSET,
            "token_out": USDC,
            "min_out": 1,
            "aux": "0x",
        }
    ]


def _envelope() -> OpportunityEnvelope:
    return OpportunityEnvelope(
        opportunity_id="opp-provider",
        route_id="route-provider",
        route_family="flash_arb",
        expected_profit_usd=10_000.0,
        gas_estimate_usd=100.0,
        slippage_sensitivity=0.01,
        liquidity_fragility=0.05,
        latency_half_life_ms=1_000,
        mempool_copy_risk=0.02,
        venue_reliability_score=0.95,
        simulation_confidence=0.95,
        safe_size_curve=[
            SafeSizePoint(1.0, 10_000.0, 100.0, 0.0, 0.0),
            SafeSizePoint(2.0, 19_000.0, 200.0, 0.0, 0.0),
        ],
        failure_cost_estimate=50.0,
        freshness_score=0.98,
        private_send_preference=True,
        chain_id=1,
        token_path=[ASSET, USDC],
        venues=[VENUE],
    )


def _sizing_contract(*, requested: float, provider_capacity: float) -> InstitutionalSizingContract:
    return InstitutionalSizingContract(
        contract_version="institutional-v1",
        strategy_family="flash_arb",
        capital_source="flashloan",
        requested_notional_usd=requested,
        target_notional_usd=5_000_000.0,
        base_borrow_amount_wei=0,
        max_borrow_amount_wei=0,
        liquidity=LiquiditySizingContext(
            available_usd=requested,
            depth_usd=requested,
            pool_depth_cap_usd=requested,
            provider_capacity_usd=provider_capacity,
            route_capacity_usd=requested,
        ),
        execution=ExecutionSizingContext(
            expected_pipeline_latency_ms=100.0,
            latency_half_life_ms=1_000.0,
            latency_pressure=0.05,
            endpoint_quality=0.99,
            venue_reliability=0.99,
            simulation_confidence=0.99,
            freshness_score=0.99,
        ),
        economics=EconomicsSizingContext(
            expected_gross_profit_usd=2_000_000.0,
            expected_net_profit_usd=1_000_000.0,
            gas_cost_usd=100.0,
            borrow_cost_usd=100.0,
            slippage_cost_usd=100.0,
            latency_cost_usd=100.0,
            failure_cost_usd=100.0,
            min_profit_usd=1.0,
            min_profit_bps=0.1,
            success_probability=0.99,
            margin_ratio=0.01,
        ),
        capital=CapitalAuthoritySizingContext(
            status="ok",
            freshness="fresh",
            authority_id="cap-provider-test",
            deployable_usd=1_000_000_000.0,
            drawdown_buffer_usd=0.0,
            family_cap_usd=1_000_000_000.0,
        ),
        wealth_goal=WealthGoalSizingContext(
            capital_commitment_pct=30.0,
            aggressiveness_cap=1.0,
            max_drawdown_pct=10.0,
            drawdown_pct=0.0,
        ),
        governance=GovernanceSizingContext(
            admitted=True,
            reason_code="ok",
            strategy_family="flash_arb",
            capital_source="flashloan",
            live_authority=False,
            execution_allowed=False,
            max_deployable_pct=1.0,
        ),
        settlement=SettlementSizingContext(),
    )


def test_unsupported_provider_fails_closed_at_calldata_boundary():
    with pytest.raises(ValueError, match="unsupported_flashloan_provider:maker"):
        build_execute_calldata(
            provider="maker",
            borrow_token=ASSET,
            amount_borrow=10,
            min_profit=1,
            profit_to=PROFIT_TO,
            deadline=123,
            legs=_legs(),
        )


def test_supported_providers_remain_executable():
    for provider in ("aave", "balancer"):
        calldata, _ = build_execute_calldata(
            provider=provider,
            borrow_token=ASSET,
            amount_borrow=10,
            min_profit=1,
            profit_to=PROFIT_TO,
            deadline=123,
            legs=_legs(),
        )
        assert calldata.startswith("0x")


def test_resilience_filters_unsupported_providers_without_fallback_to_aave():
    result = evaluate_flashloan_resilience(
        envelope=_envelope(),
        pending_metrics={"worst_case_edge": 100.0},
        route_plan={"selected_venues": [VENUE]},
        available_providers=["maker", "uniswap_flash"],
    )
    assert result["provider_priority"] == []
    assert result["selected_provider"] == ""
    assert result["fallback_provider"] == ""
    assert result["route_viable"] is False
    assert result["unsupported_providers"] == ["maker", "uniswap_flash"]
    assert "unsupported_provider" in result["reason_codes"]


def test_provider_capacity_caps_large_candidate_but_is_not_an_institutional_tier_ceiling():
    result = calculate_institutional_size(
        _sizing_contract(requested=200_000_000.0, provider_capacity=50_000_000.0)
    )
    assert result.approved_notional_usd == pytest.approx(50_000_000.0)
    assert "provider_capacity" in result.downsize_reasons

    uncapped_by_provider = calculate_institutional_size(
        _sizing_contract(requested=200_000_000.0, provider_capacity=200_000_000.0)
    )
    assert uncapped_by_provider.approved_notional_usd == pytest.approx(200_000_000.0)
    assert "provider_capacity" not in uncapped_by_provider.downsize_reasons


def test_institutional_tiers_are_design_metadata_not_flashloan_global_ceiling():
    assert [row["id"] for row in INSTITUTIONAL_V1_TIERS] == [
        "controlled_250k",
        "controlled_500k",
        "institutional_1m",
        "institutional_2_5m",
        "institutional_5m",
    ]
    assert [row["target_notional_usd"] for row in INSTITUTIONAL_V1_TIERS] == [
        250_000.0,
        500_000.0,
        1_000_000.0,
        2_500_000.0,
        5_000_000.0,
    ]
    assert all(row["enabled"] is False for row in INSTITUTIONAL_V1_TIERS)

    result = calculate_institutional_size(
        _sizing_contract(requested=200_000_000.0, provider_capacity=200_000_000.0)
    )
    assert result.approved_notional_usd == pytest.approx(200_000_000.0)
