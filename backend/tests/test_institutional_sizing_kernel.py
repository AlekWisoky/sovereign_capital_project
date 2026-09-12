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
from victor_ai_bot.execution_capture.institutional_sizing_kernel import calculate_institutional_size


def _contract(**overrides):
    values = {
        "contract_version": "institutional-v1",
        "strategy_family": "flash_arb",
        "capital_source": "flashloan",
        "requested_notional_usd": 1_000_000.0,
        "target_notional_usd": 1_000_000.0,
        "base_borrow_amount_wei": 0,
        "max_borrow_amount_wei": 0,
        "liquidity": LiquiditySizingContext(
            available_usd=2_000_000.0,
            depth_usd=1_500_000.0,
            pool_depth_cap_usd=1_200_000.0,
            provider_capacity_usd=1_500_000.0,
            route_capacity_usd=1_400_000.0,
        ),
        "execution": ExecutionSizingContext(
            expected_pipeline_latency_ms=250.0,
            latency_half_life_ms=1_200.0,
            latency_pressure=0.15,
            endpoint_quality=0.90,
            venue_reliability=0.90,
            simulation_confidence=0.92,
            freshness_score=0.95,
        ),
        "economics": EconomicsSizingContext(
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
        "capital": CapitalAuthoritySizingContext(
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
        "wealth_goal": WealthGoalSizingContext(
            capital_commitment_pct=30.0,
            aggressiveness_cap=1.0,
            max_drawdown_pct=10.0,
            drawdown_pct=1.0,
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


def test_kernel_intersects_authoritative_constraints():
    result = calculate_institutional_size(_contract())
    assert result.approved_notional_usd == pytest.approx(700_000.0)
    assert result.approved_borrow_amount_raw is None
    assert "capital_engine_deployable_pct" in result.constraints_applied
    assert "internal_prime_remaining_capacity" in result.constraints_applied
    assert "pool_depth_cap" in result.constraints_applied
    assert "wealth_goal_aggressiveness" in result.constraints_applied
    assert result.capital_utilization == pytest.approx(0.35)
    assert result.downsize_reasons


def test_kernel_is_content_deterministic_for_identical_inputs():
    first = calculate_institutional_size(_contract())
    second = calculate_institutional_size(_contract())
    assert first == second
    assert first.sizing_id == second.sizing_id


def test_kernel_uses_internal_prime_remaining_capacity():
    result = calculate_institutional_size(
        _contract(
            requested_notional_usd=2_000_000.0,
            target_notional_usd=2_000_000.0,
            capital=CapitalAuthoritySizingContext(
                status="ok",
                freshness="fresh",
                authority_id="cap-auth-2",
                deployable_usd=8_000_000.0,
                drawdown_buffer_usd=8_000_000.0,
                prime_available=True,
                prime_capacity_usd=1_000_000.0,
                prime_utilization=0.20,
                prime_reserved_usd=100_000.0,
            ),
        )
    )
    assert result.approved_notional_usd == pytest.approx(700_000.0)
    assert "internal_prime_remaining_capacity" in result.downsize_reasons


def test_kernel_never_fabricates_raw_units_without_quote_context():
    result = calculate_institutional_size(_contract())
    assert result.approved_notional_usd > 0
    assert result.approved_borrow_amount_raw is None


def test_kernel_fails_closed_on_invalid_contract():
    contract = _contract(
        capital=CapitalAuthoritySizingContext(
            status="degraded",
            freshness="stale",
            authority_id="cap-auth-bad",
            deployable_usd=2_000_000.0,
            prime_available=True,
            prime_capacity_usd=10_000_000.0,
        )
    )
    with pytest.raises(ValueError, match="institutional_sizing_contract_invalid"):
        calculate_institutional_size(contract)


def test_kernel_never_changes_live_authority():
    contract = _contract()
    result = calculate_institutional_size(contract)
    assert contract.governance.live_authority is False
    assert contract.governance.execution_allowed is False
    assert result.approved_notional_usd > 0
