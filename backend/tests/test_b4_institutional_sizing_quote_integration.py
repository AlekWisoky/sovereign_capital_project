from __future__ import annotations

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
from victor_ai_bot.execution_capture.institutional_sizing_kernel import (
    calculate_institutional_size,
)


def _contract(**overrides):
    values = {
        "contract_version": "institutional-v1",
        "strategy_family": "flash_arb",
        "capital_source": "flashloan",
        "requested_notional_usd": 250_000.0,
        "target_notional_usd": 250_000.0,
        "base_borrow_amount_wei": 0,
        "max_borrow_amount_wei": 0,
        "liquidity": LiquiditySizingContext(
            available_usd=500_000.0,
            depth_usd=500_000.0,
            pool_depth_cap_usd=500_000.0,
        ),
        "execution": ExecutionSizingContext(
            expected_pipeline_latency_ms=100.0,
            latency_half_life_ms=1000.0,
            endpoint_quality=1.0,
            venue_reliability=1.0,
            simulation_confidence=1.0,
            freshness_score=1.0,
        ),
        "economics": EconomicsSizingContext(
            expected_gross_profit_usd=1000.0,
            expected_net_profit_usd=500.0,
            min_profit_usd=1.0,
            min_profit_bps=1.0,
            success_probability=0.99,
            margin_ratio=0.01,
        ),
        "capital": CapitalAuthoritySizingContext(
            status="ok",
            freshness="fresh",
            authority_id="cap-auth-quote",
            deployable_usd=2_000_000.0,
            drawdown_buffer_usd=0.0,
            prime_available=True,
            prime_capacity_usd=2_000_000.0,
            prime_utilization=0.0,
            prime_reserved_usd=0.0,
        ),
        "wealth_goal": WealthGoalSizingContext(
            capital_commitment_pct=30.0,
            aggressiveness_cap=1.0,
            max_drawdown_pct=10.0,
            drawdown_pct=0.0,
        ),
        "governance": GovernanceSizingContext(
            admitted=True,
            reason_code="ok",
            strategy_family="flash_arb",
            capital_source="flashloan",
            live_authority=False,
            execution_allowed=False,
            max_deployable_pct=0.35,
        ),
        "settlement": SettlementSizingContext(),
        "metadata": {"behavior_change": "none"},
    }
    values.update(overrides)
    return InstitutionalSizingContract(**values)


def test_b4_final_quote_converts_approved_usd_to_raw_units():
    result = calculate_institutional_size(
        _contract(),
        final_quote={
            "quote_id": "quote-1",
            "asset_price_usd": "2500.00",
            "asset_decimals": 18,
            "block_number": 123,
        },
    )
    assert result.approved_notional_usd == pytest.approx(250_000.0)
    assert result.approved_borrow_amount_raw == 100_000_000_000_000_000_000


def test_b4_raw_hard_cap_downsizes_economic_notional():
    result = calculate_institutional_size(
        _contract(max_borrow_amount_wei=50_000_000_000_000_000_000),
        final_quote={
            "quote_id": "quote-cap",
            "asset_price_usd": "2500.00",
            "asset_decimals": 18,
            "block_number": 124,
        },
    )
    assert result.approved_borrow_amount_raw == 50_000_000_000_000_000_000
    assert result.approved_notional_usd == pytest.approx(125_000.0)
    assert "max_borrow_amount_raw" in result.constraints_applied
    assert "max_borrow_amount_raw" in result.downsize_reasons


def test_b4_missing_final_quote_preserves_b2_raw_unit_deferral():
    result = calculate_institutional_size(_contract())
    assert result.approved_notional_usd == pytest.approx(250_000.0)
    assert result.approved_borrow_amount_raw is None


def test_b4_invalid_final_quote_fails_closed():
    with pytest.raises(ValueError, match="final_quote_invalid"):
        calculate_institutional_size(
            _contract(),
            final_quote={
                "quote_id": "bad-quote",
                "asset_price_usd": 0,
                "asset_decimals": 18,
            },
        )
