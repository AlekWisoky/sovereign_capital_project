from victor_ai_bot.capital_demand import CapitalDemandInput, compose_capital_demand


def base_input(**overrides):
    values = dict(
        requested_amount=1000,
        strategy_family="flash_arb",
        strategy_version="V1",
        capital_mode="v1_external_prime",
        treasury_available=200,
        treasury_allocatable=150,
        treasury_symbol="USDC",
        treasury_decimals=6,
        conversion_authorized=True,
        conversion_rate=1.0,
        provider_capacity=5000,
        provider_fee_bps=5,
        current_exposure=0,
        exposure_limit=5000,
        risk_limit=5000,
        governance_limit=5000,
        execution_plan_required=True,
        execution_plan_ready=True,
        prime_available=1500,
        prime_capacity=1500,
        prime_fee_bps=10,
        wealth_goal_multiplier=1.0,
        aggressiveness="balanced",
        aggressiveness_cap=1.0,
        ai_multiplier=1.0,
        governance_approved=True,
        risk_approved=True,
    )
    values.update(overrides)
    return CapitalDemandInput(**values)


def test_v1_uses_external_prime_even_when_treasury_exists():
    demand = compose_capital_demand(base_input())
    assert demand.eligible is True
    assert demand.capital_mode == "v1_external_prime"
    assert demand.capital_source == "internal_prime"
    assert demand.prime_amount > 0
    assert demand.treasury_amount == 0


def test_own_capital_uses_treasury_and_exact_token_units():
    demand = compose_capital_demand(base_input(capital_mode="own_capital", requested_amount=100))
    assert demand.eligible is True
    assert demand.capital_source == "treasury"
    assert demand.treasury_amount == 100
    assert demand.prime_amount == 0
    assert demand.metadata["treasuryUnits"] == 100_000_000
    assert demand.metadata["treasuryDecimals"] == 6


def test_hybrid_fills_treasury_then_prime():
    demand = compose_capital_demand(
        base_input(capital_mode="hybrid", requested_amount=1000, treasury_allocatable=400)
    )
    assert demand.eligible is True
    assert demand.capital_source == "treasury+internal_prime"
    assert demand.treasury_amount == 400
    assert demand.prime_amount > 0


def test_wealth_goal_aggression_and_ai_shape_but_do_not_bypass_caps():
    demand = compose_capital_demand(
        base_input(
            requested_amount=1000,
            wealth_goal_multiplier=1.5,
            aggressiveness="aggressive",
            aggressiveness_cap=1.0,
            ai_multiplier=1.4,
            prime_available=600,
            prime_capacity=600,
            provider_capacity=600,
            exposure_limit=650,
            risk_limit=650,
            governance_limit=650,
        )
    )
    assert demand.shaped_amount == 1000
    assert demand.fundable_amount <= 650
    assert "demand_capped" in demand.reason_codes


def test_governance_or_risk_failure_blocks_demand():
    demand = compose_capital_demand(base_input(governance_approved=False))
    assert demand.eligible is False
    assert demand.fundable_amount >= 0
    assert "governance_not_approved" in demand.reason_codes


def test_stale_latency_blocks_execution_ready_demand():
    demand = compose_capital_demand(
        base_input(latency_ms=250, max_latency_ms=100, freshness_ms=10, max_freshness_ms=50)
    )
    assert demand.eligible is False
    assert "latency_stale" in demand.reason_codes


def test_conversion_authority_is_hard_gate_when_rate_differs():
    demand = compose_capital_demand(
        base_input(conversion_authorized=False, conversion_rate=0.99)
    )
    assert demand.eligible is False
    assert "conversion_not_authorized" in demand.reason_codes


def test_v1_can_be_selected_with_zero_treasury_because_prime_is_the_posture():
    demand = compose_capital_demand(
        base_input(
            treasury_available=0,
            treasury_allocatable=0,
            capital_mode="v1_external_prime",
            prime_available=2000,
            prime_capacity=2000,
        )
    )
    assert demand.eligible is True
    assert demand.capital_source == "internal_prime"
    assert demand.prime_amount > 0
