from types import SimpleNamespace

import pytest

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager


class _BadIntValue:
    def __int__(self):
        raise ValueError("bad int")


class _ExplodingInt:
    def __int__(self):
        raise RuntimeError("unexpected int bug")


class _BadBoolType:
    def __bool__(self):
        raise TypeError("bad bool")


class _ExplodingBool:
    def __bool__(self):
        raise RuntimeError("unexpected bool bug")


def test_bankroll_init_degrades_safely_for_expected_window_coercion_failure():
    cfg = SimpleNamespace(kelly_window=_BadIntValue())
    m = BankrollManager(cfg)
    assert m.state.recent_results.maxlen == 50
    assert m.state.recent_returns.maxlen == 50


def test_bankroll_init_does_not_swallow_unexpected_window_bug():
    cfg = SimpleNamespace(kelly_window=_ExplodingInt())
    with pytest.raises(RuntimeError, match="unexpected int bug"):
        BankrollManager(cfg)


def test_bankroll_apply_overrides_degrades_safely_for_expected_bool_failure():
    m = BankrollManager(BankrollConfig())
    before = m.cfg.kelly_enabled
    m.apply_overrides(kelly_enabled=_BadBoolType())
    assert m.cfg.kelly_enabled is before


def test_bankroll_apply_overrides_does_not_swallow_unexpected_bool_bug():
    m = BankrollManager(BankrollConfig())
    with pytest.raises(RuntimeError, match="unexpected bool bug"):
        m.apply_overrides(kelly_enabled=_ExplodingBool())
