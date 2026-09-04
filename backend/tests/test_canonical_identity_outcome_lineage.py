from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.identity import (
    attach_identity,
    identity_from,
    new_decision_identity,
    new_execution_identity,
    new_settlement_identity,
)
from victor_ai_bot.runtime_services.settled_outcome_lineage import (
    attach_settled_lineage,
    resolve_settled_lineage,
)


def test_decision_execution_settlement_identity_is_single_continuous_lineage():
    decision = new_decision_identity()
    execution = new_execution_identity(decision)
    settlement = new_settlement_identity(execution)

    assert decision.decision_id == execution.decision_id == settlement.decision_id
    assert decision.correlation_id == execution.correlation_id == settlement.correlation_id
    assert execution.execution_id
    assert settlement.settlement_id
    assert settlement.complete_for_settlement is True

    target = SimpleNamespace(metadata={})
    attach_identity(target, settlement)
    recovered = identity_from(target)

    assert recovered == settlement
    assert target.metadata["lineage"]["decision_id"] == settlement.decision_id
    assert target.metadata["lineage"]["correlation_id"] == settlement.correlation_id


def test_settled_ledger_record_resolves_identity_and_latency():
    identity = new_settlement_identity(new_execution_identity(new_decision_identity()))
    row = {
        "transaction_id": "tx-001",
        "metadata": {
            "decision_id": identity.decision_id,
            "correlation_id": identity.correlation_id,
            "execution_id": identity.execution_id,
            "sizing_id": "sizing-001",
            "outcome": {"settlement_id": identity.settlement_id, "status": "settled"},
            "latency_stages_ms": {"total": 320},
            "action": "EXECUTE",
            "opportunity_id": "opp-001",
            "chain": "ethereum",
        },
    }

    lineage = resolve_settled_lineage(row)
    enriched = attach_settled_lineage(row)

    assert lineage.complete is True
    assert lineage.decision_id == identity.decision_id
    assert lineage.correlation_id == identity.correlation_id
    assert lineage.execution_id == identity.execution_id
    assert lineage.sizing_id == "sizing-001"
    assert lineage.settlement_id == identity.settlement_id
    assert lineage.latency_class == "fast"
    assert enriched["lineage"]["complete"] is True
    assert enriched["decision_id"] == identity.decision_id
    assert enriched["correlation_id"] == identity.correlation_id
    assert enriched["execution_id"] == identity.execution_id
    assert enriched["sizing_id"] == "sizing-001"
    assert enriched["settlement_id"] == identity.settlement_id
