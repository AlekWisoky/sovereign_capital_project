from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_execute_dispatch_facade import AutoExecutionDispatchContext
from victor_ai_bot.runtime_services.runtime_execute_entry_facade import RuntimeExecuteEntryFacade


EXTRACTED_METHODS = {
    '_execute_auto_entry',
}


class _Runtime(RuntimeExecuteEntryFacade):
    def __init__(self):
        self.calls = []
        self.prep = AutoExecutionDispatchContext(
            opportunity=SimpleNamespace(route_id='prepared'),
            force_dry=True,
            old_gas_mode='standard',
            old_send_mode='public',
            read_url='read-url',
            send_url='send-url',
        )

    async def _prepare_auto_execution_dispatch(self, *, opp, bn: int, decision=None):
        self.calls.append(('prepare', {'opp': opp, 'bn': bn, 'decision': decision}))
        return self.prep

    async def _run_prepared_auto_execution(self, *, opp, bn: int, decision, prep):
        self.calls.append(
            (
                'execute',
                {
                    'opp': opp,
                    'bn': bn,
                    'decision': decision,
                    'prep': prep,
                },
            )
        )


class _RuntimeNoPrep(_Runtime):
    async def _prepare_auto_execution_dispatch(self, *, opp, bn: int, decision=None):
        self.calls.append(('prepare', {'opp': opp, 'bn': bn, 'decision': decision}))
        return None


class _RuntimeExplodes(_Runtime):
    async def _run_prepared_auto_execution(self, *, opp, bn: int, decision, prep):
        raise KeyError('unexpected execute-entry bug')


def test_runtime_bundle_inherits_execute_entry_facade():
    assert issubclass(RuntimeBundle, RuntimeExecuteEntryFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_execute_auto_entry_preserves_prepare_then_execute_order():
    runtime = _Runtime()
    opp = SimpleNamespace(route_id='raw')
    decision = SimpleNamespace(action='trade')

    await runtime._execute_auto_entry(opp=opp, bn=77, decision=decision)

    assert [name for name, _ in runtime.calls] == ['prepare', 'execute']
    assert runtime.calls[0][1] == {'opp': opp, 'bn': 77, 'decision': decision}
    execute = runtime.calls[1][1]
    assert execute['opp'] is runtime.prep.opportunity
    assert execute['bn'] == 77
    assert execute['decision'] is decision
    assert execute['prep'] is runtime.prep


@pytest.mark.asyncio
async def test_execute_auto_entry_returns_early_when_dispatch_prep_blocks():
    runtime = _RuntimeNoPrep()
    opp = SimpleNamespace(route_id='raw')

    await runtime._execute_auto_entry(opp=opp, bn=9, decision=None)

    assert [name for name, _ in runtime.calls] == ['prepare']


@pytest.mark.asyncio
async def test_execute_auto_entry_does_not_swallow_unexpected_bug():
    runtime = _RuntimeExplodes()
    with pytest.raises(KeyError, match='unexpected execute-entry bug'):
        await runtime._execute_auto_entry(opp=SimpleNamespace(route_id='raw'), bn=1, decision=None)
