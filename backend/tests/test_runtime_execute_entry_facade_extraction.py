from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_execute_dispatch_facade import (
    AutoExecutionDispatchContext,
    RuntimeExecuteDispatchFacade,
)
from victor_ai_bot.runtime_services.runtime_execute_entry_facade import RuntimeExecuteEntryFacade
from victor_ai_bot.runtime_services.runtime_execute_wrapper_facade import RuntimeExecuteWrapperFacade


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


@pytest.mark.asyncio
async def test_execute_auto_preserves_production_dispatch_chain_and_lineage(monkeypatch):
    """Lock the current RuntimeBundle._execute_auto production seam.

    This is intentionally test-only: no production method is extracted or
    rewritten. The real RuntimeBundle._execute_auto is exercised while the
    external dispatch/execution effects are replaced with deterministic test
    doubles.
    """
    runtime = RuntimeBundle.__new__(RuntimeBundle)
    opportunity = SimpleNamespace(id='opp-1', route_id='route-1')
    prepared_opportunity = SimpleNamespace(id='opp-1', route_id='route-1', prepared=True)
    decision = SimpleNamespace(
        decision_id='decision-1',
        correlation_id='corr-1',
        action='trade',
        capital_authority='internal_prime',
    )
    prep = AutoExecutionDispatchContext(
        opportunity=prepared_opportunity,
        force_dry=True,
        old_gas_mode='standard',
        old_send_mode='public',
        read_url='read-url',
        send_url='send-url',
    )
    calls = []

    async def fake_prepare(self, *, opp, bn: int, decision=None):
        calls.append(('dispatch', opp, bn, decision))
        return prep

    async def fake_execute(self, *, opp, bn: int, decision, prep):
        calls.append(('execute', opp, bn, decision, prep))

    monkeypatch.setattr(RuntimeExecuteDispatchFacade, '_prepare_auto_execution_dispatch', fake_prepare)
    monkeypatch.setattr(RuntimeExecuteWrapperFacade, '_run_prepared_auto_execution', fake_execute)

    await RuntimeBundle._execute_auto(runtime, opportunity, 77, decision)

    assert [call[0] for call in calls] == ['dispatch', 'execute']
    dispatch = calls[0]
    assert dispatch[1] is opportunity
    assert dispatch[2] == 77
    assert dispatch[3] is decision
    execute = calls[1]
    assert execute[1] is prepared_opportunity
    assert execute[2] == 77
    assert execute[3] is decision
    assert execute[4] is prep
    assert execute[3] is dispatch[3]
    assert execute[3].decision_id == 'decision-1'
    assert execute[3].correlation_id == 'corr-1'
    assert execute[3].capital_authority == 'internal_prime'


def test_execute_auto_does_not_create_a_second_identity():
    """The auto-entry method is an orchestration seam, not an identity factory."""
    source = RuntimeBundle._execute_auto.__code__
    assert 'ensure_decision_identity' not in source.co_names


@pytest.mark.asyncio
async def test_execute_auto_blocked_dispatch_never_reaches_execution(monkeypatch):
    runtime = RuntimeBundle.__new__(RuntimeBundle)
    opportunity = SimpleNamespace(id='opp-blocked')
    decision = SimpleNamespace(decision_id='decision-blocked', correlation_id='corr-blocked')
    calls = []

    async def fake_prepare(self, *, opp, bn: int, decision=None):
        calls.append(('dispatch', opp, bn, decision))
        return None

    async def fake_execute(self, *, opp, bn: int, decision, prep):
        calls.append(('execute', opp, bn, decision, prep))

    monkeypatch.setattr(RuntimeExecuteDispatchFacade, '_prepare_auto_execution_dispatch', fake_prepare)
    monkeypatch.setattr(RuntimeExecuteWrapperFacade, '_run_prepared_auto_execution', fake_execute)

    await RuntimeBundle._execute_auto(runtime, opportunity, 9, decision)

    assert [call[0] for call in calls] == ['dispatch']


@pytest.mark.asyncio
async def test_execute_auto_passes_exact_dispatch_context_to_wrapper(monkeypatch):
    runtime = RuntimeBundle.__new__(RuntimeBundle)
    raw_opportunity = SimpleNamespace(id='raw')
    prepared_opportunity = SimpleNamespace(id='prepared')
    decision = SimpleNamespace(decision_id='decision-2', correlation_id='corr-2')
    prep = AutoExecutionDispatchContext(
        opportunity=prepared_opportunity,
        force_dry=False,
        old_gas_mode='fast',
        old_send_mode='private',
        read_url='read-2',
        send_url='send-2',
    )
    seen = {}

    async def fake_prepare(self, *, opp, bn: int, decision=None):
        seen['dispatch'] = (opp, bn, decision)
        return prep

    async def fake_execute(self, *, opp, bn: int, decision, prep):
        seen['execute'] = (opp, bn, decision, prep)

    monkeypatch.setattr(RuntimeExecuteDispatchFacade, '_prepare_auto_execution_dispatch', fake_prepare)
    monkeypatch.setattr(RuntimeExecuteWrapperFacade, '_run_prepared_auto_execution', fake_execute)

    await RuntimeBundle._execute_auto(runtime, raw_opportunity, 12, decision)

    assert seen['dispatch'] == (raw_opportunity, 12, decision)
    assert seen['execute'] == (prepared_opportunity, 12, decision, prep)
    assert seen['execute'][3] is prep


@pytest.mark.asyncio
async def test_execute_auto_does_not_swallow_unexpected_execution_exception(monkeypatch):
    runtime = RuntimeBundle.__new__(RuntimeBundle)
    prep = AutoExecutionDispatchContext(
        opportunity=SimpleNamespace(id='prepared'),
        force_dry=True,
        old_gas_mode='standard',
        old_send_mode='public',
        read_url='read',
        send_url='send',
    )

    async def fake_prepare(self, *, opp, bn: int, decision=None):
        return prep

    async def fake_execute(self, *, opp, bn: int, decision, prep):
        raise KeyError('unexpected production execution bug')

    monkeypatch.setattr(RuntimeExecuteDispatchFacade, '_prepare_auto_execution_dispatch', fake_prepare)
    monkeypatch.setattr(RuntimeExecuteWrapperFacade, '_run_prepared_auto_execution', fake_execute)

    with pytest.raises(KeyError, match='unexpected production execution bug'):
        await RuntimeBundle._execute_auto(
            runtime,
            SimpleNamespace(id='raw'),
            1,
            SimpleNamespace(decision_id='decision-3', correlation_id='corr-3'),
        )
