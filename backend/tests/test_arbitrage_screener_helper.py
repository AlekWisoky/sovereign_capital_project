import math

import pytest

from victor_ai_bot.aqe.arbitrage.screener import _sigmoid


def test_sigmoid_basic_values_are_stable():
    assert _sigmoid(0.0) == pytest.approx(0.5)
    assert 0.5 < _sigmoid(1.0) < 1.0
    assert 0.0 < _sigmoid(-1.0) < 0.5


def test_sigmoid_overflow_and_parse_failures_fall_back():
    assert _sigmoid(-10_000) == 0.5
    assert _sigmoid("bad") == 0.5


def test_sigmoid_unexpected_runtime_error_is_not_swallowed(monkeypatch):
    import victor_ai_bot.aqe.arbitrage.screener as screener

    monkeypatch.setattr(screener.math, "exp", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        _sigmoid(1.0)
