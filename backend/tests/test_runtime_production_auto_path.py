from __future__ import annotations

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle


class _RuntimeProbe(RuntimeBundle):
    """Probe the real RuntimeBundle._execute_auto production entry method.

    The constructor is intentionally bypassed: this test verifies dispatch
    ownership and method-chain routing, not network/runtime initialization.
    """

    def __init__(self):
        self.calls = []

    async def _execute_auto_entry(self, *, opp, bn: int, decision=None):
        self.calls.append(
            {
                "method": "_execute_auto_entry",
                "opp": opp,
                "bn": bn,
                "decision": decision,
            }
        )


@pytest.mark.asyncio
async def test_production_execute_auto_delegates_to_canonical_entry_facade():
    runtime = _RuntimeProbe()
    opportunity = object()
    decision = object()

    await RuntimeBundle._execute_auto(
        runtime,
        opportunity,
        321,
        decision,
    )

    assert runtime.calls == [
        {
            "method": "_execute_auto_entry",
            "opp": opportunity,
            "bn": 321,
            "decision": decision,
        }
    ]


def test_runtime_bundle_mro_places_canonical_execution_facades_in_runtime():
    names = [base.__name__ for base in RuntimeBundle.__mro__]
    assert "RuntimeExecuteDispatchFacade" in names
    assert "RuntimeExecuteWrapperFacade" in names
    assert "RuntimeExecuteEntryFacade" in names
    assert names.index("RuntimeExecuteDispatchFacade") < names.index("RuntimeExecuteEntryFacade")
    assert names.index("RuntimeExecuteWrapperFacade") < names.index("RuntimeExecuteEntryFacade")
