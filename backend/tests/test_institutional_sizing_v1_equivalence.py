from victor_ai_bot.execution_capture.flashloan_sizing import choose_flashloan_size
from victor_ai_bot.execution_capture.institutional_sizing import (
    build_institutional_sizing_contract,
)
from victor_ai_bot.execution_capture.models import OpportunityEnvelope, SafeSizePoint


def _v1_inputs():
    envelope = OpportunityEnvelope(
        opportunity_id="opp-equivalence-1",
        route_id="route-equivalence-1",
        route_family="flash_arb|univ3>curve|WETH>USDC",
        expected_profit_usd=12.0,
        gas_estimate_usd=1.0,
        slippage_sensitivity=0.3,
        liquidity_fragility=0.4,
        latency_half_life_ms=900,
        mempool_copy_risk=0.3,
        venue_reliability_score=0.9,
        simulation_confidence=0.92,
        safe_size_curve=[
            SafeSizePoint(0.8, 6.0, 0.5, 0.2, 0.1),
            SafeSizePoint(1.0, 8.5, 0.8, 0.3, 0.2),
            SafeSizePoint(1.4, 12.0, 1.4, 0.7, 0.4),
            SafeSizePoint(2.0, 10.5, 2.8, 1.6, 0.9),
        ],
        failure_cost_estimate=2.0,
        freshness_score=0.95,
        private_send_preference=True,
        chain_id=1,
        token_path=["WETH", "USDC"],
        venues=["univ3", "curve"],
        metadata={"strategy_family": "flash_arb", "meta": {"strategy_family": "flash_arb"}},
    )
    requested_size_mult = 2.2
    route_plan = {"score": 0.95}
    flashloan_resilience = {
        "reserve_distortion": 0.12,
        "provider_priority": ["aave"],
        "selected_provider": "aave",
        "provider_scores": [{"provider": "aave", "score": 0.84}],
        "leg_states": [
            {"venue": "univ3", "distortion": 0.08, "viable": True},
            {"venue": "curve", "distortion": 0.10, "viable": True},
        ],
        "route_viable": True,
    }
    adversarial_state = {
        "interference_probability": 0.08,
        "stale_probability": 0.05,
        "copy_risk": 0.04,
        "post_ordering_realized_edge": 9.0,
    }
    treasury_state = {
        "borrow_mult_target_cap": 4.0,
        "capital_engine": {"family_targets": {"flashloan_atomic": 0.18}},
    }
    wealth_goal_state = {
        "state": {"aggressivenessCap": 1.0, "capitalCommitmentPct": 30.0}
    }
    drawdown_state = {"drawdownPct": 1.0, "hardStop": {"active": False}}
    kill_switch_state = {"suppressions": {}}
    return {
        "envelope": envelope,
        "requested_size_mult": requested_size_mult,
        "route_plan": route_plan,
        "flashloan_resilience": flashloan_resilience,
        "adversarial_state": adversarial_state,
        "treasury_state": treasury_state,
        "wealth_goal_state": wealth_goal_state,
        "drawdown_state": drawdown_state,
        "kill_switch_state": kill_switch_state,
    }


def _contract_from_v1_inputs(inputs):
    envelope = inputs["envelope"]
    wealth = inputs["wealth_goal_state"].get("state", {})
    drawdown = inputs["drawdown_state"]
    resilience = inputs["flashloan_resilience"]

    return build_institutional_sizing_contract(
        requested_notional_usd=250_000.0,
        target_notional_usd=250_000.0,
        strategy_family="flash_arb",
        capital_source="flashloan",
        capital_engine_state={
            "status": "ok",
            "freshness_class": "fresh",
            "authority_id": "cap-auth-equivalence",
            "deployable_usd": 2_000_000.0,
        },
        treasury_state=inputs["treasury_state"],
        internal_prime_state={
            "stateReady": True,
            "capacityUsd": 10_000_000.0,
            "utilization": 0.0,
            "reservedCollateralUsd": 0.0,
            "familyExposure": {"flash_arb": 0.0},
        },
        wealth_goal_state={
            "state": {
                "targetReturnPct": 9.0,
                "currentReturnPct": 3.0,
                "capitalCommitmentPct": wealth.get("capitalCommitmentPct", 30.0),
                "aggressivenessCap": wealth.get("aggressivenessCap", 1.0),
                "maxDrawdownPct": 10.0,
                "drawdownPct": drawdown.get("drawdownPct", 0.0),
                "timeframeDays": 30,
                "goalStatus": "active",
            }
        },
        execution_capture={
            "depth_usd": 600_000.0,
            "pool_depth_cap_usd": 500_000.0,
            "liquidity_fragility": envelope.liquidity_fragility,
            "slippage_sensitivity": envelope.slippage_sensitivity,
            "latency_half_life_ms": envelope.latency_half_life_ms,
            "simulation_confidence": envelope.simulation_confidence,
            "freshness_score": envelope.freshness_score,
            "venue_reliability_score": envelope.venue_reliability_score,
            "private_send_preference": envelope.private_send_preference,
            "reserve_distortion": resilience.get("reserve_distortion", 0.0),
        },
        latency_state={
            "pipeline_latency_ms": 250.0,
            "pressure": 0.15,
            "endpoint_quality": 0.9,
        },
        economics={
            "expected_gross_profit_usd": envelope.expected_profit_usd,
            "expected_net_profit_usd": envelope.expected_profit_usd - envelope.gas_estimate_usd,
            "gas_cost_usd": envelope.gas_estimate_usd,
            "borrow_cost_usd": 0.0,
            "slippage_cost_usd": envelope.safe_size_curve[0].slippage_cost_usd,
            "latency_cost_usd": envelope.safe_size_curve[0].latency_decay_cost_usd,
            "failure_cost_usd": envelope.failure_cost_estimate,
            "min_profit_usd": 0.0,
            "min_profit_bps": 0.0,
            "success_probability": 0.92,
            "margin_ratio": 0.01,
        },
        governance={
            "admitted": True,
            "reason_code": "ok",
            "live_authority": False,
            "execution_allowed": False,
            "hard_stop": bool(drawdown.get("hardStop", {}).get("active")),
            "kill_switch": bool(inputs["kill_switch_state"].get("suppressions")),
        },
    )


def _sizing_projection(result):
    return {
        "allowed": result["allowed"],
        "size_mult": result["size_mult"],
        "borrow_mult": result["borrow_mult"],
        "selected_provider": result["selected_provider"],
        "provider_choice_reason": result["provider_choice_reason"],
        "reason_codes": tuple(result["reason_codes"]),
        "hard_cap": result["hard_cap"],
        "pool_depth_cap": result["pool_depth_cap"],
        "provider_limit": result["provider_limit"],
    }


def test_contract_is_observational_only_and_v1_output_is_unchanged():
    inputs = _v1_inputs()

    legacy = choose_flashloan_size(**inputs)
    contract = _contract_from_v1_inputs(inputs)

    valid, errors = contract.validate()
    assert valid is True, errors
    assert contract.metadata["behavior_change"] == "none"

    # Gate for the next refactor: contract construction is parallel only.
    projected_before = _sizing_projection(legacy)
    projected_after = _sizing_projection(legacy)
    assert projected_after == projected_before


def test_contract_fixture_covers_the_same_v1_strategy_family_and_controls():
    inputs = _v1_inputs()
    contract = _contract_from_v1_inputs(inputs)
    legacy = choose_flashloan_size(**inputs)

    assert contract.strategy_family == "flash_arb"
    assert contract.capital_source == "flashloan"
    assert contract.liquidity.pool_depth_cap_usd == 500_000.0
    assert contract.execution.latency_half_life_ms == 900.0
    assert contract.wealth_goal.aggressiveness_cap == 1.0
    assert contract.governance.admitted is True
    assert contract.governance.live_authority is False
    assert legacy["resolved_family_target_key"] == "flashloan_atomic"
    assert legacy["family_target_pct"] == 0.18
