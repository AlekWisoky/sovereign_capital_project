from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


class _Runtime(RuntimeDecisionFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="test"),
            execution=SimpleNamespace(brain_mode="off", max_pending_txs=1),
        )
        self._auto_trading = True
        self._opps = [SimpleNamespace(id="opp-1", can_execute=True, meta={"safety": {"exec_ready": True}})]
        self._pending = {}
        self._auto_queue = []
        self._exec_task = None
        self._cb = SimpleNamespace(allow_auto_trading=lambda: True)
        self._scheduled = []

    def _opp_is_exec_ready(self, opp):
        return True

    async def _execute_auto(self, opp, bn, decision=None):
        self._scheduled.append((opp, bn, decision))


def test_brain_mode_off_does_not_bypass_canonical_decision():
    runtime = _Runtime()
    assert runtime._maybe_dispatch_auto_trade(current_block=123, decision=None) is False
    assert runtime._exec_task is None


@pytest.mark.asyncio
async def test_brain_mode_off_uses_existing_canonical_decision():
    runtime = _Runtime()
    decision = SimpleNamespace(action="trade", portfolio=["opp-1"], opp_id="opp-1")
    assert runtime._maybe_dispatch_auto_trade(current_block=123, decision=decision) is True
    await runtime._exec_task
    assert runtime._scheduled == [(runtime._opps[0], 123, decision)]
