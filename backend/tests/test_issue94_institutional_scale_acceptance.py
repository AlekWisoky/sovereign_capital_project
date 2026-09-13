from __future__ import annotations

from dataclasses import replace

import pytest

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
from victor_ai_bot.execution_capture.institutional_sizing_kernel import calculate_institutional_size


def _institutional_contract(target_usd: float) -> InstitutionalSizingContract:
    return InstitutionalSizingContract(
        contract_version="institutional-v1",
        strategy_family="flash_arb",
        capital_source="flashloan",
        requested_notional_usd=target_usd,
        target_notional_usd=target_usd,
        base_borrow_amount_wei=0,
        max_borrow_amount_wei=0,
        liquidity=LiquiditySizingContext(
            available_usd=500_000_000.0,
            depth_usd=500_000_000.0,
            pool_depth_cap_usd=500_000_000.0,
            provider_capacity_usd=500_000_000.0,
            route_capacity_usd=500_000_000.0,
        ),
        execution=ExecutionSizingContext(
            expected_pipeline_latency_ms=100.0,
            latency_half_life_ms=1000.0,
            endpoint_quality=1.0,
            venue_reliability=1.0,
            simulation_confidence=1.0,
            freshness_score=1.0,
        ),
        economics=EconomicsSizingContext(
            expected_gross_profit_usd=target_usd * 0.02,
            expected_net_profit_usd=target_usd * 0.01,
            min_profit_usd=1.0,
            min_profit_bps=1.0,
            success_probability=0.99,
            margin_ratio=0.01,
        ),
        capital=CapitalAuthoritySizingContext(
            status="ok",
            freshness="fresh",
            authority_id="cap-auth-issue94-scale",
            deployable_usd=1_000_000_000.0,
            drawdown_buffer_usd=0.0,
            prime_available=True,
            prime_capacity_usd=500_000_000.0,
            prime_utilization=0.0,
            prime_reserved_usd=0.0,
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
            max_deployable_pct=0.5,
        ),
        settlement=SettlementSizingContext(),
        metadata={"behavior_change": "none"},
    )


@pytest.mark.parametrize(
    "target_usd",
    [250_000.0, 500_000.0, 1_000_000.0, 2_500_000.0, 5_000_000.0, 50_000_000.0, 100_000_000.0, 200_000_000.0],
)
def test_institutional_scale_matrix_preserves_canonical_sizing_and_quote_lineage(target_usd: float):
    contract = _institutional_contract(target_usd)
    base = calculate_institutional_size(contract)
    quoted = calculate_institutional_size(
        contract,
        final_quote={
            "quote_id": f"quote-scale-{int(target_usd)}",
            "asset_price_usd": 2500.0,
            "asset_decimals": 18,
            "block_number": int(target_usd),
        },
    )

    assert base.sizing_id == quoted.sizing_id
    assert quoted.approved_notional_usd == pytest.approx(target_usd)
    assert quoted.execution_notional_usd == pytest.approx(target_usd)
    assert quoted.quote_id == f"quote-scale-{int(target_usd)}"
    assert quoted.approved_borrow_amount_raw is not None
    assert "sizing_id" not in quoted.quote_id
    assert quoted.downsize_reasons == ()


def test_institutional_scale_matrix_uses_explicit_prime_capacity_not_ten_million_default():
    target_usd = 500_000_000.0
    contract = _institutional_contract(target_usd)
    result = calculate_institutional_size(
        contract,
        final_quote={
            "quote_id": "quote-scale-500m",
            "asset_price_usd": 2500.0,
            "asset_decimals": 18,
            "block_number": 500_000_000,
        },
    )

    assert result.approved_notional_usd == pytest.approx(500_000_000.0)
    assert result.execution_notional_usd == pytest.approx(500_000_000.0)
    assert result.sizing_id
    assert result.quote_id == "quote-scale-500m"


def test_institutional_scale_matrix_still_downsizes_above_explicit_capacity():
    contract = _institutional_contract(1_000_000_000.0)
    result = calculate_institutional_size(
        contract,
        final_quote={
            "quote_id": "quote-scale-1b",
            "asset_price_usd": 2500.0,
            "asset_decimals": 18,
            "block_number": 1_000_000_000,
        },
    )

    assert result.approved_notional_usd == pytest.approx(500_000_000.0)
    assert result.execution_notional_usd == pytest.approx(500_000_000.0)
    assert result.downsize_reasons
    assert any(reason in result.downsize_reasons for reason in ("liquidity_available", "pool_depth", "pool_depth_cap", "provider_capacity", "route_capacity", "internal_prime_remaining_capacity"))
