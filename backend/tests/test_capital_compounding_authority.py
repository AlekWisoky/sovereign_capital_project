from victor_ai_bot.treasury.capital_compounding import resolve_profit_promotion


def test_capital_engine_is_authority_for_incremental_profit_promotion() -> None:
    out = resolve_profit_promotion(
        capital_engine={
            "profit_promotion_enabled": True,
            "profit_promotion_rate_pct": 40.0,
            "deployable_bankroll_wei": 25 * 10**18,
        },
        realized_profit_wei=5 * 10**18,
        reinvestment_policy={"reinvest_pct": 0.58},
        previous_promoted_profit_wei=1 * 10**18,
    )

    assert out["authority"] == "capital_engine_state"
    assert out["rate_pct"] == 40.0
    assert out["eligible_profit_wei"] == 2 * 10**18
    assert out["promoted_profit_delta_wei"] == 1 * 10**18
    assert out["deployable_bankroll_after_wei"] == 26 * 10**18
    assert out["promotion_applied"] is True


def test_capital_engine_promotion_is_idempotent_for_same_settled_profit() -> None:
    out = resolve_profit_promotion(
        capital_engine={
            "profit_promotion_enabled": True,
            "profit_promotion_rate_pct": 40.0,
            "deployable_bankroll_wei": 26 * 10**18,
        },
        realized_profit_wei=5 * 10**18,
        reinvestment_policy={"reinvest_pct": 0.58},
        previous_promoted_profit_wei=2 * 10**18,
    )

    assert out["promoted_profit_delta_wei"] == 0
    assert out["deployable_bankroll_after_wei"] == 26 * 10**18
    assert out["reason_code"] == "profit_already_promoted"


def test_disabled_capital_engine_promotion_never_increases_deployable() -> None:
    out = resolve_profit_promotion(
        capital_engine={
            "profit_promotion_enabled": False,
            "profit_promotion_rate_pct": 100.0,
            "deployable_bankroll_wei": 10 * 10**18,
        },
        realized_profit_wei=4 * 10**18,
        reinvestment_policy={"reinvest_pct": 100.0},
    )

    assert out["eligible_profit_wei"] == 0
    assert out["promoted_profit_delta_wei"] == 0
    assert out["deployable_bankroll_after_wei"] == 10 * 10**18
    assert out["reason_code"] == "profit_promotion_disabled"
