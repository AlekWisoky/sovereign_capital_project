from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_capital_facade import RuntimeCapitalFacade


EXTRACTED_METHODS = {
    'wealth_goal_state',
    'record_ledger_entry',
    'stress_evaluate',
}


class _AuxiliaryStateService:
    def wealth_goal_state(self, runtime):
        return {'state': {'targetUsd': 1500, 'aggressivenessCap': 1.1}}


class _Entry:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _Ledger:
    def __init__(self):
        self.last = None

    def append(self, **kwargs):
        self.last = dict(kwargs)
        return _Entry({'ok': True, **kwargs})


class _LedgerRepo:
    def __init__(self):
        self.calls = []

    def append(self, **kwargs):
        self.calls.append(dict(kwargs))


class _PnL:
    async def summary(self, window: int = 100):
        return {'total_realized_profit_after_gas_usd': 1000.0, 'window': window}


class _Runtime(RuntimeCapitalFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name='ethereum'))
        self._auxiliary_state_service = _AuxiliaryStateService()
        self._ledger = _Ledger()
        self._ledger_repo = _LedgerRepo()
        self._pnl = _PnL()
        self._fioa = SimpleNamespace(last_stress=0.5)


def test_runtime_bundle_inherits_extracted_capital_facade():
    assert issubclass(RuntimeBundle, RuntimeCapitalFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_capital_facade_preserves_wealth_goal_and_ledger_surface():
    runtime = _Runtime()

    assert runtime.wealth_goal_state()['state']['targetUsd'] == 1500

    item = runtime.record_ledger_entry(
        entry_type='borrow',
        asset='WETH',
        amount=12.5,
        venue='dex-a',
        family='flashloan_atomic',
        note='maintenance-test',
    )
    assert item['ok'] is True
    assert runtime._ledger.last['chain'] == 'ethereum'
    assert runtime._ledger_repo.calls[0]['chain'] == 'ethereum'
    assert runtime._ledger_repo.calls[0]['payload']['family'] == 'flashloan_atomic'


def test_runtime_capital_facade_stress_evaluate_remains_deterministic():
    runtime = _Runtime()

    result = __import__('asyncio').run(runtime.stress_evaluate(scenario='gas_5x'))

    assert result['ok'] is True
    assert result['scenario'] == 'gas_5x'
    assert result['currentNavUsd'] == 1000.0
    assert result['riskScore'] == 50.0
    assert result['triggeredBreaker'] == 'gasAnomalyBreaker'
    assert result['projectedNavUsd'] < result['currentNavUsd']


def test_runtime_capital_facade_safe_defaults_hold_when_deps_missing():
    runtime = _Runtime()
    runtime._ledger = SimpleNamespace(append=lambda **kwargs: (_ for _ in ()).throw(RuntimeError('boom')))
    runtime._ledger_repo = None
    runtime._pnl = SimpleNamespace()
    runtime._fioa = None

    assert runtime.record_ledger_entry(entry_type='pnl', asset='USDC', amount=1.0) == {}
    result = __import__('asyncio').run(runtime.stress_evaluate())
    assert result['ok'] is True
    assert result['currentNavUsd'] == 0.0
    assert result['riskScore'] == 0.0
