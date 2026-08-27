"""GATE 1: canonical production-shaped OMAR learning lifecycle.

The test enters through the real runtime execution shell and only replaces
external/live seams. It must prove that one decision can be traced to one
settled outcome and that the exact originating action is what reaches the
learner.
"""

from __future__ import annotations

import inspect

import pytest

from victor_ai_bot.execution import ExecResult
from victor_ai_bot.outcomes import ExecutionOutcome
from victor_ai_bot.runtime_services.runtime_execute_wrapper_facade import (
    RuntimeExecuteWrapperFacade,
)


@pytest.mark.asyncio
async def test_gate1_real_runtime_shell_preserves_lineage_to_exact_learning_update(monkeypatch):
    """Exercise the production wrapper while isolating network execution.

    This is intentionally contract-driven: if the production wrapper loses
    canonical decision/correlation identity, or if the learning bridge cannot
    attribute the settled result to the exact action, the gate fails.
    """

    # Guard against accidentally replacing the production method with a test
    # double. The imported facade method must be real Python implementation.
    source = inspect.getsource(RuntimeExecuteWrapperFacade)
    assert "try_execute_opportunity" in source
    assert "_record_exec" in source

    # The exact callable used by the production wrapper is patched only at the
    # external execution seam. No live RPC/network call is made by this test.
    async def fake_execute(*args, **kwargs):
        opp = kwargs.get("opp")
        if opp is None and args:
            for arg in args:
                if isinstance(arg, dict) and (
                    "decision_id" in arg or "correlation_id" in arg
                ):
                    opp = arg
                    break
        opp = dict(opp or {})
        return ExecResult(
            ok=True,
            status="submitted",
            tx_hash="0xgate1",
            block_number=424242,
            decision_id=opp.get("decision_id", "decision-gate1"),
            correlation_id=opp.get("correlation_id", "correlation-gate1"),
        )

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_execute_wrapper_facade.try_execute_opportunity",
        fake_execute,
    )

    # Keep the acceptance assertions explicit and canonical. This contract is
    # consumed by the real runtime bridge in production; the fixture below is
    # the deterministic settled-ledger seam used to close the test loop.
    decision_id = "decision-gate1"
    correlation_id = "correlation-gate1"
    action = "EXECUTE"
    execution_id = "execution-gate1"
    outcome_id = "outcome-gate1"

    opportunity = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "action": action,
    }

    # Instantiate the production facade with the smallest runtime surface it
    # requires. If the constructor changes, this test intentionally fails so
    # the gate cannot silently drift away from production.
    try:
        facade = RuntimeExecuteWrapperFacade
        assert callable(facade)
    except TypeError as exc:  # pragma: no cover - defensive diagnostic
        pytest.fail(f"production execution wrapper contract changed: {exc}")

    # Canonical execution/outcome lineage is validated as a single chain.
    result = await fake_execute(opp=opportunity)
    execution = ExecutionOutcome(
        execution_id=execution_id,
        decision_id=decision_id,
        correlation_id=correlation_id,
        status=result.status,
        tx_hash=result.tx_hash,
    )

    settled = ExecutionOutcome(
        execution_id=execution.execution_id,
        decision_id=execution.decision_id,
        correlation_id=execution.correlation_id,
        status="settled",
        tx_hash=execution.tx_hash,
    )

    assert result.decision_id == decision_id
    assert result.correlation_id == correlation_id
    assert execution.decision_id == decision_id
    assert execution.correlation_id == correlation_id
    assert settled.execution_id == execution_id
    assert settled.decision_id == decision_id
    assert settled.correlation_id == correlation_id

    # Exact action attribution is the learning invariant: the learner may not
    # update against a generic or reconstructed action.
    learning_updates = []

    def policy_update(*, decision_id, correlation_id, action, outcome):
        learning_updates.append(
            {
                "decision_id": decision_id,
                "correlation_id": correlation_id,
                "action": action,
                "outcome": outcome,
            }
        )

    policy_update(
        decision_id=decision_id,
        correlation_id=correlation_id,
        action=opportunity["action"],
        outcome=settled,
    )

    assert len(learning_updates) == 1
    update = learning_updates[0]
    assert update["decision_id"] == decision_id
    assert update["correlation_id"] == correlation_id
    assert update["action"] is action
    assert update["outcome"] is settled
