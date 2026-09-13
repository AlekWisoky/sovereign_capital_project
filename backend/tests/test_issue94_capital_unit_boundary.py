from __future__ import annotations

from victor_ai_bot.engine_control.admission_governor import EngineAdmissionGovernor
from victor_ai_bot.engine_control.capability_registry import default_engine_capability_registry
from victor_ai_bot.engine_control.models import EngineOpportunity
from victor_ai_bot.treasury.engine_capital_policy import engine_capital_limits


def _opportunity() -> EngineOpportunity:
    return EngineOpportunity(
        opportunity_id="issue94-unit-boundary",
        engine_type="funding_arb",
        strategy_family="funding_arb",
        route_family="funding",
        chain="ethereum",
        chain_id=1,
        expected_profit_usd=500.0,
        expected_realized_profit_usd=450.0,
        capital_required_usd=100.0,
        inventory_requirements={},
        confidence=0.95,
        regime="normal",
        latency_sensitivity=0.2,
        lifecycle_eligibility="paper",
        policy_eligibility="observe_only",
    )


def test_admission_never_treats_raw_wei_as_usd():
    governor = EngineAdmissionGovernor(default_engine_capability_registry())
    result = governor.decide(
        opportunity=_opportunity(),
        env_mode="paper",
        telemetry_points=30,
        calibration_points=10,
        treasury_state={
            "capital_engine": {"deployable_bankroll_wei": 1_000_000_000_000_000_000_000_000}
        },
    )

    assert result.allowed is False
    assert result.reason == "capital_economic_value_unavailable"
    assert result.max_capital_usd == 0.0
    assert result.max_size_mult == 0.0


def test_admission_uses_only_explicit_deployable_usd():
    governor = EngineAdmissionGovernor(default_engine_capability_registry())
    result = governor.decide(
        opportunity=_opportunity(),
        env_mode="paper",
        telemetry_points=30,
        calibration_points=10,
        treasury_state={"capital_engine": {"deployable_usd": 1_000.0}},
    )

    assert result.allowed is True
    assert result.max_capital_usd == 220.0
    assert result.details["economic_value_source"] == "capital_engine.deployable_usd"


def test_engine_capital_limits_do_not_convert_raw_wei_to_usd():
    result = engine_capital_limits(
        engine_type="funding_arb",
        treasury_state={
            "capital_engine": {
                "deployable_bankroll_wei": 5_000_000_000_000_000_000,
                "family_allocations_wei": {"funding_arb": 1_000_000_000_000_000_000},
            }
        },
    )

    assert result["deployable_capital_usd"] == 0.0
    assert result["family_capital_usd"] == 0.0
    assert result["economic_value_source"] == "unavailable"
    assert result["family_economic_value_source"] == "unavailable"


def test_engine_capital_limits_accept_explicit_usd_values():
    result = engine_capital_limits(
        engine_type="funding_arb",
        treasury_state={
            "capital_engine": {
                "deployable_usd": 1_500_000.0,
                "family_allocations_usd": {"funding_arb": 500_000.0},
            }
        },
    )

    assert result["deployable_capital_usd"] == 1_500_000.0
    assert result["family_capital_usd"] == 500_000.0
    assert result["economic_value_source"] == "capital_engine.deployable_usd"
    assert result["family_economic_value_source"] == "capital_engine.family_allocations_usd"
