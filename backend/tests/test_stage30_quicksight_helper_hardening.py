from __future__ import annotations

import pytest

from victor_ai_bot.analytics.quicksight.query_engine import _safe_float
from victor_ai_bot.analytics.quicksight.scenario import simulate_scenario


class _BadFloatValue:
    def __float__(self):
        raise ValueError("bad_float")

    def __str__(self) -> str:
        return "1.25"


class _BoomFloat:
    def __float__(self):
        raise RuntimeError("boom_float")


class _BoomStr:
    def __float__(self):
        raise TypeError("fallback_to_str")

    def __str__(self) -> str:
        raise RuntimeError("boom_str")


class _BrokenRow:
    def get(self, key, default=None):
        raise RuntimeError(f"boom_get:{key}")


def test_safe_float_expected_coercion_failures_degrade_safely():
    assert _safe_float(_BadFloatValue(), 0.0) == pytest.approx(1.25)
    assert _safe_float(object(), 3.5) == pytest.approx(3.5)


def test_safe_float_unexpected_bugs_are_not_swallowed():
    with pytest.raises(RuntimeError, match="boom_float"):
        _safe_float(_BoomFloat(), 0.0)

    with pytest.raises(RuntimeError, match="boom_str"):
        _safe_float(_BoomStr(), 0.0)


def test_simulate_scenario_expected_funding_shape_failures_degrade_safely():
    out = simulate_scenario(
        base_metrics={"win_rate": 0.5, "sharpe_ratio": 1.0, "drawdown": 0.1},
        income={"by_income_stream": {"funding": 5}},
        hypothetical_volatility_change=0.0,
        capital_shift=0.0,
        funding_rate_spike=0.5,
        aggressiveness_adjustment=0.0,
    )
    assert out["projected"]["pnl_scale"] == pytest.approx(1.0)


def test_simulate_scenario_unexpected_funding_bugs_are_not_swallowed():
    with pytest.raises(RuntimeError, match="boom_get"):
        simulate_scenario(
            base_metrics={"win_rate": 0.5, "sharpe_ratio": 1.0, "drawdown": 0.1},
            income={"by_income_stream": {"funding": _BrokenRow()}},
            hypothetical_volatility_change=0.0,
            capital_shift=0.0,
            funding_rate_spike=0.5,
            aggressiveness_adjustment=0.0,
        )
