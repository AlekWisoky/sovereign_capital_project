from victor_ai_bot.treasury.compounding_runtime import CompoundingTreasuryRuntime
from victor_ai_bot.treasury.config import TreasuryConfig


def test_runtime_promotes_settled_profit_into_next_capital_engine_snapshot(tmp_path) -> None:
    cfg = TreasuryConfig(enabled=True, data_dir=str(tmp_path), estimated_capital_wei=10 * 10**18)
    cfg.meta["estimated_capital_wei"] = 10 * 10**18
    cfg.meta["auto_reinvest_enabled"] = True

    runtime = CompoundingTreasuryRuntime(cfg=cfg, data_dir=str(tmp_path), chain="test")
    first = runtime.pre_select_strategy(
        bankroll_state={
            "realized_profit_wei": 2 * 10**18,
            "last_amount_in_wei": 10**18,
        },
        persist=True,
    )

    engine = first["capital_engine"]
    assert engine["promotion_authority"] == "capital_engine_state"
    assert engine["promoted_profit_wei"] > 0
    assert engine["promotion_delta_wei"] > 0
    assert engine["estimated_capital_wei"] > 10 * 10**18
    assert engine["deployable_bankroll_wei"] > 0

    second = runtime.pre_select_strategy(
        bankroll_state={
            "realized_profit_wei": 2 * 10**18,
            "last_amount_in_wei": 10**18,
        },
        persist=True,
    )
    second_engine = second["capital_engine"]
    assert second_engine["promotion_delta_wei"] == 0
    assert second_engine["promoted_profit_wei"] == engine["promoted_profit_wei"]


def test_runtime_compounding_is_disabled_without_auto_reinvest(tmp_path) -> None:
    cfg = TreasuryConfig(enabled=True, data_dir=str(tmp_path), estimated_capital_wei=10 * 10**18)
    cfg.meta["estimated_capital_wei"] = 10 * 10**18
    cfg.meta["auto_reinvest_enabled"] = False

    runtime = CompoundingTreasuryRuntime(cfg=cfg, data_dir=str(tmp_path), chain="test")
    snapshot = runtime.pre_select_strategy(
        bankroll_state={
            "realized_profit_wei": 2 * 10**18,
            "last_amount_in_wei": 10**18,
        },
        persist=False,
    )

    promotion = snapshot["capital_compounding"]
    assert promotion["promoted_profit_delta_wei"] == 0
    assert promotion["reason_code"] == "profit_promotion_disabled"
