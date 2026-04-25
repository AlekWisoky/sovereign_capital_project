import pytest

from victor_ai_bot.income import _safe_str, classify_opportunity_income


class _Opp:
    def __init__(self, strategy):
        self.strategy = strategy


def test_income_safe_str_keeps_expected_coercion_behavior():
    assert _safe_str(123) == "123"


def test_income_safe_str_does_not_swallow_unexpected_bug():
    class BadStr:
        def __str__(self):
            raise RuntimeError("unexpected_str_bug")

    with pytest.raises(RuntimeError, match="unexpected_str_bug"):
        _safe_str(BadStr())


def test_classify_opportunity_income_derives_expected_categories():
    opp = _Opp("two-leg:uniswapv3->curve")
    strategy_type, income_stream, venue_path = classify_opportunity_income(opp)
    assert strategy_type == "dex_flash_2leg"
    assert income_stream == "flash_arb"
    assert venue_path == "uniswapv3->curve"
