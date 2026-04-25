from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_decision_finalize_facade import RuntimeDecisionFinalizeFacade

EXTRACTED_METHODS = {
    '_run_decision_finalize',
}


class _Runtime(RuntimeDecisionFinalizeFacade):
    def __init__(self):
        self._pending = [object(), object()]
        self._auto_trading = True
        self.calls = []

    def _gas_budget_remaining_wei(self):
        self.calls.append(('gas_budget', None))
        return 12345

    def _safe_decide_opportunities(self, opps, **kwargs):
        self.calls.append(('decide', {'opps': opps, **dict(kwargs)}))
        return SimpleNamespace(action='trade', borrow_mult=1.0, portfolio=['a', 'b'])

    def _apply_treasury_borrow_overlay(self, **kwargs):
        self.calls.append(('treasury_overlay', dict(kwargs)))
        decision = kwargs['decision']
        decision.borrow_mult = 1.25
        return decision

    def _refresh_auto_queue_from_decision(self, decision, *, current_block: int):
        self.calls.append(('auto_queue', {'decision': decision, 'current_block': current_block}))
        return True

    async def _run_postdecision_analytics_state(self, **kwargs):
        self.calls.append(('postdecision', dict(kwargs)))
        return None


class _RuntimeExplodes(_Runtime):
    def _safe_decide_opportunities(self, opps, **kwargs):
        raise KeyError('unexpected decision finalize bug')


def test_runtime_bundle_inherits_decision_finalize_facade():
    assert issubclass(RuntimeBundle, RuntimeDecisionFinalizeFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_run_decision_finalize_preserves_call_order_and_arguments():
    runtime = _Runtime()
    opps = [SimpleNamespace(id='o1')]
    rpc = object()

    decision = await runtime._run_decision_finalize(
        opps=opps,
        rpc=rpc,
        regime_label='balanced',
        treasury_state={'borrow_mult_target_cap': 1.5},
        current_block=77,
        loop_started_at=12.5,
    )

    assert decision.action == 'trade'
    assert decision.borrow_mult == 1.25
    assert [name for name, _ in runtime.calls] == [
        'gas_budget',
        'decide',
        'treasury_overlay',
        'auto_queue',
        'postdecision',
    ]
    decide = runtime.calls[1][1]
    assert decide['current_block'] == 77
    assert decide['pending_txs'] == 2
    assert decide['auto_enabled'] is True
    assert decide['gas_budget_remaining_wei'] == 12345
    overlay = runtime.calls[2][1]
    assert overlay['treasury_state'] == {'borrow_mult_target_cap': 1.5}
    auto_queue = runtime.calls[3][1]
    assert auto_queue['current_block'] == 77
    postdecision = runtime.calls[4][1]
    assert postdecision['rpc'] is rpc
    assert postdecision['regime_label'] == 'balanced'
    assert postdecision['current_block'] == 77
    assert postdecision['loop_started_at'] == 12.5


@pytest.mark.asyncio
async def test_run_decision_finalize_does_not_swallow_unexpected_bug():
    runtime = _RuntimeExplodes()
    with pytest.raises(KeyError, match='unexpected decision finalize bug'):
        await runtime._run_decision_finalize(
            opps=[],
            rpc=object(),
            regime_label='balanced',
            treasury_state=None,
            current_block=1,
            loop_started_at=1.0,
        )
