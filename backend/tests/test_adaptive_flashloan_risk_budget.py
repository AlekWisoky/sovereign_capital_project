from victor_ai_bot.execution_capture.adaptive_flashloan_risk_budget import (
    build_risk_budget,
    choose_adaptive_size,
    compute_profit_after_costs,
    learning_reward_from_settled_outcome,
)


def test_profit_after_costs_includes_flashloan_fee_and_execution_costs():
    result = compute_profit_after_costs(
        gross_profit_usd=100.0,
        flashloan_fee_usd=8.0,
        gas_cost_usd=12.0,
        slippage_cost_usd=15.0,
        execution_fee_usd=5.0,
        prime_cost_usd=3.0,
        safety_reserve_usd=7.0,
        capital_base_usd=1000.0,
    )
    assert result.net_profit_usd == 50.0
    assert result.net_roi_bps == 500.0


def test_risk_budget_hard_gates_and_preference_signals():
    budget = build_risk_budget(
        capital_available_usd=100_000,
        deployable_capital_usd=60_000,
        family_allocation_usd=20_000,
        max_borrow_usd=15_000,
        max_loss_usd=1_000,
        current_drawdown_pct=1.0,
        hard_stop=False,
        governance_allowed=True,
        capital_authority_fresh=True,
        confidence=0.9,
        aggressiveness=1.0,
        goal_gap_pct=10.0,
    )
    assert 0.0 < budget <= 1_000

    assert build_risk_budget(
        capital_available_usd=100_000,
        deployable_capital_usd=60_000,
        family_allocation_usd=20_000,
        max_borrow_usd=15_000,
        max_loss_usd=1_000,
        current_drawdown_pct=1.0,
        hard_stop=True,
        governance_allowed=True,
        capital_authority_fresh=True,
        confidence=1.0,
        aggressiveness=1.0,
        goal_gap_pct=10.0,
    ) == 0.0


def test_adaptive_sizer_prefers_largest_profitable_size_within_budget():
    result = choose_adaptive_size(
        canonical_decision_id="decision-8",
        correlation_id="corr-8",
        route_id="route-8",
        provider="aave",
        requested_size_mult=2.0,
        candidates=[
            {"size_mult": 1.0, "net_profit_usd": 25.0, "net_roi_bps": 180.0, "estimated_loss_usd": 30.0},
            {"size_mult": 2.0, "net_profit_usd": 70.0, "net_roi_bps": 210.0, "estimated_loss_usd": 60.0},
            {"size_mult": 3.0, "net_profit_usd": 100.0, "net_roi_bps": 220.0, "estimated_loss_usd": 140.0},
        ],
        risk_budget_usd=75.0,
        minimum_net_profit_usd=20.0,
        minimum_net_roi_bps=150.0,
        expected_loss_ratio=40.0,
        max_size_mult=3.0,
    )
    assert result.allowed is True
    assert result.selected_size_mult == 2.0
    assert result.sizing_id.startswith("sizing_")
    assert result.canonical_decision_id == "decision-8"
    assert result.correlation_id == "corr-8"


def test_adaptive_sizer_fails_closed_without_canonical_identity():
    result = choose_adaptive_size(
        canonical_decision_id="",
        correlation_id="corr-9",
        route_id="route-9",
        provider="aave",
        requested_size_mult=2.0,
        candidates=[{"size_mult": 2.0, "net_profit_usd": 100.0, "net_roi_bps": 500.0}],
        risk_budget_usd=1_000.0,
        minimum_net_profit_usd=1.0,
        minimum_net_roi_bps=1.0,
        expected_loss_ratio=1.0,
        max_size_mult=3.0,
    )
    assert result.allowed is False
    assert result.reason == "missing_canonical_identity"


def test_learning_reward_uses_settled_net_profit_not_gross():
    assert learning_reward_from_settled_outcome(
        {
            "truth_verified": True,
            "realized_net_usd": 40.0,
            "expected_net_usd": 20.0,
        }
    ) == 45.0
    assert learning_reward_from_settled_outcome(
        {
            "truth_verified": False,
            "realized_net_usd": 100.0,
            "expected_net_usd": 20.0,
        }
    ) == 0.0
