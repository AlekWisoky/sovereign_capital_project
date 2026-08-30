from victor_ai_bot.execution_capture.flashloan_sizing import choose_flashloan_size
from victor_ai_bot.execution_capture.models import OpportunityEnvelope, SafeSizePoint


def _envelope():
    return OpportunityEnvelope(
        opportunity_id="opp-24",
        route_id="route-24",
        route_family="flashloan_atomic|univ3>curve|WETH>WETH",
        expected_profit_usd=100.0,
        gas_estimate_usd=2.0,
        slippage_sensitivity=0.1,
        liquidity_fragility=0.2,
        latency_half_life_ms=1000,
        mempool_copy_risk=0.1,
        venue_reliability_score=0.9,
        simulation_confidence=0.9,
        safe_size_curve=[
            SafeSizePoint(0.5, 30.0, 2.0, 1.0, 1.0),
            SafeSizePoint(1.0, 70.0, 4.0, 2.0, 2.0),
        ],
        failure_cost_estimate=2.0,
        freshness_score=0.9,
        private_send_preference=False,
        chain_id=1,
        token_path=["WETH", "USDC", "WETH"],
        venues=["univ3", "curve"],
        metadata={
            "strategy_family": "flashloan_atomic",
            "meta": {
                "canonical_decision_id": "decision-24",
                "correlation_id": "corr-24",
            },
        },
    )


def test_choose_flashloan_size_runs_adaptive_controller_in_canonical_entrypoint():
    result = choose_flashloan_size(
        envelope=_envelope(),
        requested_size_mult=1.0,
        route_plan={"score": 1.0},
        flashloan_resilience={
            "provider_priority": ["aave"],
            "provider_scores": [{"provider": "aave", "score": 0.95}],
            "selected_provider": "aave",
            "fallback_provider": "aave",
            "route_viable": True,
            "reserve_distortion": 0.05,
            "leg_states": [{"viable": True, "distortion": 0.05}],
        },
        adversarial_state={
            "interference_probability": 0.05,
            "stale_probability": 0.05,
            "copy_risk": 0.05,
            "post_ordering_realized_edge": 70.0,
        },
        treasury_state={
            "capital_engine": {
                "capital_available_usd": 100000.0,
                "deployable_capital_usd": 60000.0,
                "family_allocation_usd": 20000.0,
                "max_borrow_usd": 15000.0,
                "max_loss_usd": 1000.0,
            }
        },
        wealth_goal_state={"aggressivenessCap": 1.0, "capitalCommitmentPct": 25.0, "goalGapPct": 10.0},
        drawdown_state={"drawdownPct": 1.0, "hardStop": False},
        kill_switch_state={},
    )
    assert result["adaptive_controller"] == "phase23"
    assert result["canonical_decision_id"] == "decision-24"
    assert result["correlation_id"] == "corr-24"
    assert result["sizing_id"].startswith("sizing_")
    assert result["adaptive_risk_budget"]["canonical_decision_id"] == "decision-24"


def test_choose_flashloan_size_preserves_legacy_behavior_without_canonical_identity():
    result = choose_flashloan_size(
        envelope=_envelope(),
        requested_size_mult=1.0,
        route_plan={"score": 1.0},
        flashloan_resilience={"provider_priority": ["aave"], "selected_provider": "aave", "route_viable": True},
        adversarial_state={"post_ordering_realized_edge": 70.0},
    )
    assert "adaptive_controller" not in result
    assert "size_mult" in result
