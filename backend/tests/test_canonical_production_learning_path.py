from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.identity import (
    TradeIdentity,
    attach_identity,
    identity_from,
    new_execution_identity,
    new_settlement_identity,
)
from victor_ai_bot.omar.real_learning import OmarRealLearningLoop
from victor_ai_bot.omar.settled_ledger_bridge import ingest_settled_ledger_record


def test_empty_identity_recovery_is_not_treated_as_existing_identity():
    assert identity_from(SimpleNamespace()) is None
    assert identity_from({}) is None
    assert identity_from({"identity": {}, "lineage": {}}) is None


def test_recovery_prefers_existing_canonical_lineage_over_empty_identity_shell():
    identity = TradeIdentity(
        decision_id="decision_1",
        correlation_id="corr_1",
        execution_id="exec_1",
        settlement_id="settle_1",
    )
    recovered = identity_from(
        {
            "identity": {},
            "lineage": identity.to_dict(),
        }
    )
    assert recovered == identity


def test_callable_canonical_production_learning_path_preserves_exact_action_attribution(
    tmp_path,
):
    updates = []
    loop = OmarRealLearningLoop(
        chain_name="ethereum",
        data_dir=str(tmp_path),
        capital_authority_reader=lambda: {
            "authority_id": "internal-prime-1",
            "available_wei": 1_000_000,
            "allocatable_wei": 800_000,
            "family_allocatable_wei": {"flashloan_atomic": 250_000},
            "status": "authoritative",
            "freshness_class": "fresh",
            "source": "internal_prime",
        },
        policy_updater=lambda attribution: updates.append(attribution) or {
            "updated": True,
            "learning_id": attribution.learning_id,
        },
    )

    decision_identity = TradeIdentity("decision_1", "corr_1")
    decision = SimpleNamespace(action="trade", opp_id="opp_1", route_id="route_1")
    attach_identity(decision, decision_identity)

    execution_identity = new_execution_identity(decision_identity)
    execution = SimpleNamespace(action="trade", plan={})
    attach_identity(execution, execution_identity)

    # This is the same settled-ledger payload shape the runtime bridge consumes:
    # identity is immutable lineage; outcome economics remain settled truth.
    settlement_identity = new_settlement_identity(execution_identity)
    settled_row = {
        "transaction_id": "tx-1",
        "receipt_id": "0xabc",
        "chain": "ethereum",
        "decision_id": settlement_identity.decision_id,
        "correlation_id": settlement_identity.correlation_id,
        "execution_id": settlement_identity.execution_id,
        "settlement_id": settlement_identity.settlement_id,
        "action": "trade",
        "opportunity_id": "opp_1",
        "route_id": "route_1",
        "policy_version": "policy_1",
        "status": "settled",
        "metadata": {
            "decision_id": decision_identity.decision_id,
            "correlation_id": decision_identity.correlation_id,
            "execution_id": execution_identity.execution_id,
            "settlement_id": settlement_identity.settlement_id,
            "action": decision.action,
            "opportunity_id": decision.opp_id,
            "route_id": decision.route_id,
            "policy_version": "policy_1",
            "status": "settled",
            "realized_profit_after_gas_wei": 900,
            "gas_cost_wei": 100,
            "risk_cost_wei": 25,
            "latency_stages_ms": {"total": 120},
            "execution": {"status": "filled", "action": "trade"},
        },
    }

    loop.record_decision(
        decision_id=decision_identity.decision_id,
        correlation_id=decision_identity.correlation_id,
        action=decision.action,
        opp_id=decision.opp_id,
        route_id=decision.route_id,
    )
    loop.bind_execution(
        decision_id=execution_identity.decision_id,
        correlation_id=execution_identity.correlation_id,
        execution_id=execution_identity.execution_id,
        status="filled",
        action=execution.action,
        tx_hash="0xabc",
        latency_ms=120,
    )

    result = ingest_settled_ledger_record(loop, settled_row)

    assert result["ok"] is True
    assert result["eligible_for_learning"] is True
    lineage = result["lineage"]
    assert lineage["decision_id"] == decision_identity.decision_id
    assert lineage["correlation_id"] == decision_identity.correlation_id
    assert lineage["execution_id"] == execution_identity.execution_id
    assert lineage["settlement_id"] == settlement_identity.settlement_id
    assert lineage["action"] == "trade"
    assert lineage["latency_class"] == "fast"
    assert result["attribution"]["action"] == decision.action
    assert result["attribution"]["reward_wei"] == 775
    assert result["attribution"]["decision_id"] == decision_identity.decision_id
    assert result["attribution"]["execution_id"] == execution_identity.execution_id
    assert result["attribution"]["settlement_id"] == settlement_identity.settlement_id
    assert len(updates) == 1
    assert updates[0].action == decision.action
    assert updates[0].reward_wei == 775
    assert loop._decisions[decision_identity.decision_id].capital_authority.authority_id == "internal-prime-1"
    assert loop._decisions[decision_identity.decision_id].capital_authority.family_allocatable_wei["flashloan_atomic"] == 250_000
