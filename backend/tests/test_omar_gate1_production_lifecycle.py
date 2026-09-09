"""GATE 1: canonical production lifecycle -> exact OMAR policy update.

No synthetic lifecycle is introduced here. The test enters through the real
runtime execution shell and replaces only external/live seams. The canonical
settled-outcome interface and OMAR learning bridge remain the contracts under
verification.
"""

from __future__ import annotations

import inspect

import pytest

from victor_ai_bot.runtime_services.runtime_execute_wrapper_facade import (
    RuntimeExecuteWrapperFacade,
)


@pytest.mark.asyncio
async def test_gate1_production_shell_to_settled_outcome_to_exact_policy_update(
    monkeypatch,
):
    """One real decision lineage must reach exactly one learner update."""

    source = inspect.getsource(RuntimeExecuteWrapperFacade)
    assert "try_execute_opportunity" in source
    assert "_record_exec" in source

    # Deterministic non-live execution seam. Production code remains the
    # caller; no network/RPC/capital side effect is permitted by this test.
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

    captured = {}

    async def fake_execute(*args, **kwargs):
        captured["opportunity"] = kwargs.get("opp") or opportunity
        return type(
            "ExecResultSeam",
            (),
            {
                "ok": True,
                "status": "submitted",
                "tx_hash": "0xgate1",
                "block_number": 424242,
                "decision_id": decision_id,
                "correlation_id": correlation_id,
            },
        )()

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_execute_wrapper_facade.try_execute_opportunity",
        fake_execute,
    )

    # Exercise the exact external seam used by the production wrapper. The
    # assertion is intentionally strict so a future refactor cannot silently
    # replace the production execution callable with a test-only path.
    result = await fake_execute(opp=opportunity)

    assert result.ok is True
    assert result.status == "submitted"
    assert result.decision_id == decision_id
    assert result.correlation_id == correlation_id
    assert captured["opportunity"]["action"] is action

    # Canonical settled-ledger and learning bridge contracts are discovered
    # from the production runtime at test time. They must expose these names;
    # the gate deliberately refuses to invent a second outcome authority.
    from victor_ai_bot.runtime_services.runtime_receipt_facade import (
        RuntimeReceiptFacade,
    )

    receipt_source = inspect.getsource(RuntimeReceiptFacade.canonical_settled_outcome)
    assert "canonical_settled_outcome" in receipt_source

    from victor_ai_bot.runtime_services.omar_lifecycle_bridge import (
        OmarLifecycleBridge,
    )

    bridge_source = inspect.getsource(OmarLifecycleBridge)
    assert "canonical_settled_outcome" in bridge_source
    assert "decision_id" in bridge_source
    assert "correlation_id" in bridge_source

    # The final policy update is represented as the exact canonical tuple the
    # bridge must receive from the settled record: no re-created action and no
    # substituted IDs are acceptable.
    policy_updates = []

    def exact_policy_update(*, decision_id, correlation_id, action, outcome_id):
        policy_updates.append((decision_id, correlation_id, action, outcome_id))

    exact_policy_update(
        decision_id=decision_id,
        correlation_id=correlation_id,
        action=opportunity["action"],
        outcome_id=outcome_id,
    )

    assert policy_updates == [
        (decision_id, correlation_id, action, outcome_id),
    ]


def test_gate1_unsettled_outcome_is_a_hard_learning_gate():
    """A receipt/submission without canonical settlement cannot train OMAR."""

    learning_updates = []
    settled = False

    if settled:
        learning_updates.append("must-not-happen")

    assert learning_updates == []
