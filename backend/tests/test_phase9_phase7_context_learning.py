from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.identity import TradeIdentity
from victor_ai_bot.omar.settled_ledger_bridge import ingest_settled_ledger_record
from victor_ai_bot.runtime_services.phase7_context import (
    attach_phase7_execution_context,
    build_phase7_execution_context,
)
from victor_ai_bot.runtime_services.phase7_context_store import Phase7ContextStore
from victor_ai_bot.runtime_services.settled_outcome_lineage import resolve_settled_lineage


def test_phase7_context_reuses_decision_snapshot_without_hot_path_state_reads():
    expected = {
        "schema_version": 1,
        "decision": {
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "action": "EXECUTE",
        },
        "operator_intent": {"aggression_mode": "balanced"},
        "runtime_access": {"wealth_goal": {"target_amount": "100000"}},
    }
    decision = SimpleNamespace(
        action="EXECUTE",
        metadata={"phase7_context": expected},
        identity=TradeIdentity("decision-1", "corr-1"),
    )
    runtime = SimpleNamespace()
    opp = SimpleNamespace(meta={})

    context = build_phase7_execution_context(runtime, opp, decision)

    assert context["decision"]["decision_id"] == "decision-1"
    assert context["decision"]["correlation_id"] == "corr-1"
    assert context["decision"]["action"] == "EXECUTE"
    assert context["operator_intent"]["aggression_mode"] == "balanced"


def test_phase7_context_attaches_to_execution_plan_and_opportunity():
    context = {
        "decision": {
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "action": "EXECUTE",
        }
    }
    result = SimpleNamespace(plan={})
    opp = SimpleNamespace(meta={})

    attach_phase7_execution_context(result, context)
    attach_phase7_execution_context(opp, context)

    assert result.plan["phase7_context"] == context
    assert result.plan["lineage"] == {
        "decision_id": "decision-1",
        "correlation_id": "corr-1",
        "action": "EXECUTE",
    }
    assert opp.meta["phase7_context"] == context


def test_settled_lineage_requires_exact_action_for_learning():
    row = {
        "decision_id": "decision-1",
        "correlation_id": "corr-1",
        "execution_id": "exec-1",
        "settlement_id": "settle-1",
    }
    lineage = resolve_settled_lineage(row)
    assert lineage.complete is False
    assert "missing_action" in lineage.reason_codes


def test_omar_bridge_reads_phase7_context_by_transaction_and_preserves_lineage(tmp_path):
    store = Phase7ContextStore(data_dir=str(tmp_path), chain="ethereum")
    phase7 = {
        "schema_version": 1,
        "decision": {
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "action": "EXECUTE",
            "policy_version": "policy-7",
        },
        "operator_intent": {
            "aggression_mode": "aggressive",
            "desired_wealth_goal": {"target_amount": "100000", "timeframe_days": 180},
        },
    }
    assert store.put("0xabc", phase7)

    class Loop:
        chain_name = "ethereum"
        data_dir = str(tmp_path)

        def __init__(self):
            self._decisions = {}
            self._executions = {}
            self.last_update = {"updated": True}
            self.calls = []

        def record_decision(self, **kwargs):
            self.calls.append(("decision", kwargs))
            self._decisions[kwargs["decision_id"]] = kwargs

        def bind_execution(self, **kwargs):
            self.calls.append(("execution", kwargs))
            self._executions[kwargs["execution_id"]] = kwargs

        def settle_outcome(self, **kwargs):
            self.calls.append(("outcome", kwargs))
            return SimpleNamespace(
                eligible_for_learning=True,
                to_dict=lambda: {"eligible_for_learning": True},
            )

    loop = Loop()
    row = {
        "tx_hash": "0xabc",
        "decision_id": "decision-1",
        "correlation_id": "corr-1",
        "execution_id": "exec-1",
        "settlement_id": "settle-1",
        "action": "EXECUTE",
        "status": "settled",
        "route_id": "route-1",
    }

    result = ingest_settled_ledger_record(loop, row)

    assert result["ok"] is True
    assert result["eligible_for_learning"] is True
    assert result["phase7_context"]["operator_intent"]["aggression_mode"] == "aggressive"
    assert result["lineage"]["action"] == "EXECUTE"
    assert loop.calls[-1][0] == "outcome"
