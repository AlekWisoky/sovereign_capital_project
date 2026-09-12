from victor_ai_bot.execution_capture.institutional_sizing import (
    INSTITUTIONAL_V1_TIERS,
    build_institutional_sizing_contract,
)


def _contract(**overrides):
    values = {
        "requested_notional_usd": 250_000.0,
        "strategy_family": "flash_arb",
        "capital_source": "flashloan",
        "capital_engine_state": {
            "status": "ok",
            "freshness_class": "fresh",
            "authority_id": "cap-auth-1",
            "deployable_usd": 2_000_000.0,
        },
        "treasury_state": {"capital_engine": {"family_targets": {"flash_arb": 0.25}}},
        "internal_prime_state": {
            "stateReady": True,
            "borrowedUsd": 0.0,
            "capacityUsd": 10_000_000.0,
            "utilization": 0.0,
            "familyExposure": {"flash_arb": 0.0},
        },
        "wealth_goal_state": {
            "state": {
                "targetReturnPct": 9.0,
                "currentReturnPct": 3.0,
                "capitalCommitmentPct": 25.0,
                "aggressivenessCap": 1.0,
                "maxDrawdownPct": 10.0,
                "drawdownPct": 1.0,
                "timeframeDays": 30,
                "goalStatus": "active",
            }
        },
        "execution_capture": {
            "depth_usd": 600_000.0,
            "pool_depth_cap_usd": 500_000.0,
            "liquidity_fragility": 0.2,
            "slippage_sensitivity": 0.2,
            "latency_half_life_ms": 1200,
            "simulation_confidence": 0.92,
            "freshness_score": 0.95,
            "venue_reliability_score": 0.9,
        },
        "latency_state": {"pipeline_latency_ms": 250.0, "pressure": 0.15, "endpoint_quality": 0.9},
        "economics": {
            "expected_gross_profit_usd": 180.0,
            "expected_net_profit_usd": 120.0,
            "gas_cost_usd": 8.0,
            "borrow_cost_usd": 12.0,
            "slippage_cost_usd": 20.0,
            "latency_cost_usd": 5.0,
            "failure_cost_usd": 15.0,
            "min_profit_usd": 5.0,
            "min_profit_bps": 2.0,
            "success_probability": 0.92,
            "margin_ratio": 0.01,
        },
        "governance": {
            "admitted": True,
            "reason_code": "ok",
            "live_authority": False,
            "execution_allowed": False,
        },
        "base_borrow_amount_wei": 0,
        "max_borrow_amount_wei": 0,
    }
    values.update(overrides)
    return build_institutional_sizing_contract(**values)


def test_contract_maps_authoritative_domains_without_changing_size():
    contract = _contract(target_notional_usd=250_000.0)
    valid, errors = contract.validate()
    assert valid is True
    assert errors == ()
    assert contract.requested_notional_usd == 250_000.0
    assert contract.liquidity.pool_depth_cap_usd == 500_000.0
    assert contract.execution.latency_half_life_ms == 1200.0
    assert contract.capital.deployable_usd == 2_000_000.0
    assert contract.wealth_goal.aggressiveness_cap == 1.0
    assert contract.governance.admitted is True
    assert contract.governance.live_authority is False
    assert contract.metadata["behavior_change"] == "none"


def test_contract_fails_closed_when_capital_authority_is_missing():
    contract = _contract(
        capital_engine_state={
            "status": "unavailable",
            "freshness_class": "unavailable",
            "authority_id": "",
        }
    )
    valid, errors = contract.validate()
    assert valid is False
    assert "capital_authority_unavailable" in errors
    assert "capital_authority_stale" in errors
    assert "deployable_capital_missing" in errors


def test_contract_does_not_treat_wei_as_usd():
    contract = _contract(
        capital_engine_state={
            "status": "ok",
            "freshness_class": "fresh",
            "authority_id": "cap-auth-wei-only",
            "deployable_bankroll_wei": 10**18,
        }
    )
    assert contract.capital.deployable_usd is None
    valid, errors = contract.validate()
    assert valid is False
    assert "deployable_capital_missing" in errors


def test_institutional_tiers_are_design_only_and_disabled():
    ids = [row["id"] for row in INSTITUTIONAL_V1_TIERS]
    amounts = [row["target_notional_usd"] for row in INSTITUTIONAL_V1_TIERS]
    assert ids == ["controlled_250k", "controlled_500k", "institutional_1m", "institutional_2m"]
    assert amounts == [250_000.0, 500_000.0, 1_000_000.0, 2_000_000.0]
    assert all(row["enabled"] is False for row in INSTITUTIONAL_V1_TIERS)


def test_internal_prime_requires_prime_authority():
    contract = _contract(
        capital_source="internal_prime",
        capital_engine_state={
            "status": "ok",
            "freshness_class": "fresh",
            "authority_id": "cap-auth-1",
            "deployable_usd": 2_000_000.0,
            "internal_prime_available": False,
        },
        internal_prime_state={
            "stateReady": False,
            "stateStatus": "unavailable",
            "capacityUsd": 10_000_000.0,
        },
    )
    valid, errors = contract.validate()
    assert valid is False
    assert "internal_prime_unavailable" in errors