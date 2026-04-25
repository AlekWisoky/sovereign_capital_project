import math

import pytest

from victor_ai_bot.aqe.spread.formulas import alpha_score, logistic, net_profit_usd


def test_spread_formulas_keep_expected_numeric_behavior():
    assert net_profit_usd(spread=0.01, volume=1000.0, fees_usd=1.0, slippage_usd=1.0) == pytest.approx(8.0)
    assert alpha_score(profit_usd=10.0, capital_usd=100.0) == pytest.approx(0.1)
    assert logistic(0.0) == pytest.approx(0.5)


def test_logistic_expected_coercion_failures_degrade_safely():
    assert logistic('bad') == pytest.approx(0.5)
    assert logistic(-10_000.0) == pytest.approx(0.5)


def test_logistic_does_not_swallow_unexpected_runtime_errors():
    class BadFloat:
        def __float__(self):
            raise RuntimeError('boom')

    with pytest.raises(RuntimeError):
        logistic(BadFloat())
