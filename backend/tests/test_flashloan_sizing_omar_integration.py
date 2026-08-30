from victor_ai_bot.execution_capture.flashloan_sizing_integration import apply_adaptive_flashloan_controller


def test_adaptive_controller_is_applied_to_existing_sizing_result():
    result = apply_adaptive_flashloan_controller(
        legacy_result={
            "allowed": True,
            "selected_provider": "aave",
            "size_mult": 1.0,
            "borrow_mult": 1.0,
            "net_edge": 70.0,
            "resolved_family_target_key": "arbitrage",
            "provider_candidates": [
                {
                    "provider": "aave",
                    "candidates": [
                        {"size_mult": 1.0, "net_edge": 30.0},
                        {"size_mult": 2.0, "net_edge": 70.0},
                    ],
                }
            ],
        },
        canonical_decision_id="decision-24",
        correlation_id="corr-24",
        route_id="route-24",
        provider="aave",
        requested_size_mult=2.0,
        capital_engine_state={
            "capital_available_usd": 100000.0,
            "deployable_capital_usd": 60000.0,
            "family_allocation_usd": 20000.0,
        },
        treasury_state=None,
        wealth_goal_state={"aggressivenessCap": 1.0, "capitalCommitmentPct": 25.0},
        drawdown_state={"drawdownPct": 1.0, "hardStop": False},
        governance_allowed=True,
        capital_authority_fresh=True,
        confidence=0.9,
        aggressiveness=1.0,
        goal_gap_pct=10.0,
        max_borrow_usd=15000.0,
        max_loss_usd=1000.0,
        minimum_net_profit_usd=20.0,
        minimum_net_roi_bps=150.0,
        expected_loss_ratio=40.0,
        max_size_mult=3.0,
    )
    assert result["adaptive_allowed"] is True
    assert result["sizing_id"].startswith("sizing_")
    assert result["canonical_decision_id"] == "decision-24"
    assert result["correlation_id"] == "corr-24"


def test_adaptive_controller_fails_closed_when_capital_authority_denies():
    result = apply_adaptive_flashloan_controller(
        legacy_result={"allowed": True, "selected_provider": "aave", "size_mult": 1.0, "net_edge": 50.0},
        canonical_decision_id="decision-25",
        correlation_id="corr-25",
        route_id="route-25",
        provider="aave",
        requested_size_mult=1.0,
        capital_engine_state={"capital_available_usd": 1000.0, "deployable_capital_usd": 1000.0, "family_allocation_usd": 1000.0},
        treasury_state=None,
        wealth_goal_state=None,
        drawdown_state={"drawdownPct": 1.0, "hardStop": False},
        governance_allowed=False,
        capital_authority_fresh=True,
        confidence=1.0,
        aggressiveness=1.0,
        goal_gap_pct=0.0,
        max_borrow_usd=1000.0,
        max_loss_usd=100.0,
        minimum_net_profit_usd=1.0,
        minimum_net_roi_bps=1.0,
        expected_loss_ratio=10.0,
        max_size_mult=3.0,
    )
    assert result["adaptive_allowed"] is False
    assert result["allowed"] is False
