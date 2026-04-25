from __future__ import annotations

import types
import sys

import pytest

from victor_ai_bot.aqe.core.actions import ActionSpec, actions_from_rl


class _FakeAction:
    def __init__(self, *, size_mult=1.0, borrow_mult=1.0, gas_mode='standard'):
        self.size_mult = size_mult
        self.borrow_mult = borrow_mult
        self.gas_mode = gas_mode


class _BadFloat:
    def __float__(self):
        raise RuntimeError('unexpected bug')


def test_actions_from_rl_falls_back_when_rl_policy_missing(monkeypatch):
    monkeypatch.delitem(sys.modules, 'victor_ai_bot.rl_policy', raising=False)

    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'victor_ai_bot.rl_policy':
            raise ModuleNotFoundError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr('builtins.__import__', fake_import)

    actions = actions_from_rl()

    assert actions == [
        ActionSpec(1.0, 1.0, 'standard'),
        ActionSpec(0.75, 1.0, 'standard'),
        ActionSpec(0.5, 1.0, 'standard'),
        ActionSpec(1.0, 1.0, 'fast'),
    ]


def test_actions_from_rl_accepts_valid_policy_module(monkeypatch):
    fake_module = types.ModuleType('victor_ai_bot.rl_policy')

    class FakeRlPolicy:
        ACTIONS = [_FakeAction(size_mult='1.25', borrow_mult='0.5', gas_mode='fast')]

        @staticmethod
        def ensure_actions():
            return None

    fake_module.RlPolicy = FakeRlPolicy
    monkeypatch.setitem(sys.modules, 'victor_ai_bot.rl_policy', fake_module)

    actions = actions_from_rl()

    assert actions == [ActionSpec(1.25, 0.5, 'fast')]


def test_actions_from_rl_does_not_swallow_unexpected_runtime_bug(monkeypatch):
    fake_module = types.ModuleType('victor_ai_bot.rl_policy')

    class FakeRlPolicy:
        ACTIONS = [_FakeAction(size_mult=_BadFloat(), borrow_mult=1.0, gas_mode='standard')]

        @staticmethod
        def ensure_actions():
            return None

    fake_module.RlPolicy = FakeRlPolicy
    monkeypatch.setitem(sys.modules, 'victor_ai_bot.rl_policy', fake_module)

    with pytest.raises(RuntimeError):
        actions_from_rl()
