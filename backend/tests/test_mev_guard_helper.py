from types import SimpleNamespace

import pytest

from victor_ai_bot.aqe.mev.guard import MEVGuard
from victor_ai_bot.aqe.mev.models import MEVConfig


class _RuntimeRaises:
    def state(self):
        raise RuntimeError('boom')


class _RuntimeMissingState:
    pass


class _BadDex:
    def __str__(self):
        raise RuntimeError('bad dex stringify')


class _Leg:
    def __init__(self, dex):
        self.dex = dex


def _cfg() -> MEVConfig:
    return MEVConfig(enabled=True, high_risk_threshold=0.75)


def test_mev_guard_missing_state_degrades_cleanly():
    guard = MEVGuard(cfg=_cfg(), mev_runtime=_RuntimeMissingState())
    opp = SimpleNamespace(route=SimpleNamespace(legs=[]))
    decision = guard.assess(opp=opp, send_mode='public')
    assert decision.allow is True
    assert decision.risk == 0.0
    assert decision.reason == 'ok'


def test_mev_guard_runtime_error_from_state_not_swallowed():
    guard = MEVGuard(cfg=_cfg(), mev_runtime=_RuntimeRaises())
    opp = SimpleNamespace(route=SimpleNamespace(legs=[]))
    with pytest.raises(RuntimeError):
        guard.assess(opp=opp, send_mode='public')


def test_mev_guard_runtime_error_from_dex_stringify_not_swallowed():
    runtime = SimpleNamespace(state=lambda: {'sandwich_risk_p90': 0.1, 'high_risk_ratio': 0.1})
    guard = MEVGuard(cfg=_cfg(), mev_runtime=runtime)
    opp = SimpleNamespace(route=SimpleNamespace(legs=[_Leg(_BadDex())]))
    with pytest.raises(RuntimeError):
        guard.assess(opp=opp, send_mode='public')
