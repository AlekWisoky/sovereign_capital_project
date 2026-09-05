from types import SimpleNamespace

import pytest

from victor_ai_bot.identity import attach_identity, new_decision_identity
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


class _Runtime(RuntimeDecisionFacade):
    def __init__(self, *, brain_mode="off"):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(brain_mode=brain_mode, max_pending_txs=1)
        )
        self._pending = {}
        self._opps = []
        self._auto_queue = []
        self._auto_trading = True
        self._exec_task = None
        self._scheduled = []
        self._cb = SimpleNamespace(allow_auto_trading=lambda: True)

    async def _execute_auto(self, opp, bn, decision=None):
        self._scheduled.append((opp, bn, decision))


def _opp(opp_id="chosen"):
    return SimpleNamespace(
        id=opp_id,
        route_id="route-1",
        can_execute=True,
        meta={
            "safety": {"exec_ready": True, "profit_after_costs_wei": "5"},
            "profitability": {
                "stage": "post_execution_revalidation",
                "source": "execution",
                "reason": "verified",
                "revalidated": True,
                "stale": False,
                "valid": True,
                "authoritative": True,
                "profit_after_costs_wei": "5",
            },
        },
    )


def _decision(action="skip"):
    decision = SimpleNamespace(
        action=action,
        opp_id="",
        route_id="",
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
        reason="brain_off",
        metadata={"economic_context": {"expected_profit_wei": "5"}},
    )
    attach_identity(decision, new_decision_identity())
    return decision


@pytest.mark.asyncio
async def test_brain_off_forwards_canonical_decision_identity_into_execution():
    runtime = _Runtime(brain_mode="off")
    runtime._opps = [_opp()]
    decision = _decision()

    assert decision.action == "skip"
    assert decision.decision_id
    assert decision.correlation_id

    assert runtime._maybe_dispatch_auto_trade(current_block=123, decision=decision) is True
    await runtime._exec_task

    chosen, block, forwarded = runtime._scheduled[0]
    assert chosen.id == "chosen"
    assert block == 123
    assert forwarded is not decision
    assert forwarded.action == "trade"
    assert forwarded.reason == "baseline_selected"
    assert forwarded.decision_id == decision.decision_id
    assert forwarded.correlation_id == decision.correlation_id
    assert forwarded.metadata["execution_forwarding"] == {
        "selection_source": "baseline_auto_candidate",
        "omar_influence": False,
        "brain_mode": "off",
    }
    assert forwarded.metadata["economic_context"] == decision.metadata["economic_context"]


@pytest.mark.asyncio
async def test_brain_auto_forwards_same_canonical_decision_object():
    runtime = _Runtime(brain_mode="auto")
    runtime._opps = [_opp("omar-choice")]
    decision = _decision(action="trade")
    decision.opp_id = "omar-choice"
    decision.route_id = "route-1"
    decision.portfolio = ["omar-choice"]

    assert runtime._maybe_dispatch_auto_trade(current_block=456, decision=decision) is True
    await runtime._exec_task

    chosen, block, forwarded = runtime._scheduled[0]
    assert chosen.id == "omar-choice"
    assert block == 456
    assert forwarded is decision
    assert forwarded.decision_id == decision.decision_id
    assert forwarded.correlation_id == decision.correlation_id


@pytest.mark.asyncio
async def test_real_execution_fails_closed_when_canonical_decision_is_missing():
    runtime = _Runtime(brain_mode="off")
    runtime._opps = [_opp()]

    assert runtime._maybe_dispatch_auto_trade(current_block=789, decision=None) is False
    assert runtime._exec_task is None
    assert runtime._scheduled == []
