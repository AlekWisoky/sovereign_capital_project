from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.models import Opportunity
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


class _Runtime(RuntimeDecisionFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(brain_mode="off", max_pending_txs=1)
        )
        self._cb = SimpleNamespace(allow_auto_trading=lambda: True)
        self._auto_trading = True
        self._opps = [SimpleNamespace(id="opp-1")]
        self._pending = {}
        self._exec_task = None
        self.calls = []

    @staticmethod
    def _opp_is_exec_ready(_opp):
        return True

    async def _execute_auto(self, opp: Opportunity, bn: int, decision=None):
        self.calls.append((opp, bn, decision))


@pytest.mark.asyncio
async def test_brain_off_forwards_decision_to_execution_entry():
    runtime = _Runtime()
    decision = SimpleNamespace(
        decision_id="decision-002",
        correlation_id="corr-002",
        action="trade",
    )

    assert runtime._maybe_dispatch_auto_trade(current_block=456, decision=decision)
    await runtime._exec_task

    assert len(runtime.calls) == 1
    _, bn, forwarded = runtime.calls[0]
    assert bn == 456
    assert forwarded is decision
    assert forwarded.decision_id == "decision-002"
    assert forwarded.correlation_id == "corr-002"
