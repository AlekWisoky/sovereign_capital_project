from __future__ import annotations

from victor_ai_bot.omar.real_learning import OmarRealLearningLoop
from victor_ai_bot.omar.settled_ledger_bridge import ingest_settled_ledger_record


def _loop(captured):
    return OmarRealLearningLoop(
        chain_name="ethereum",
        data_dir="data/test-omar-canonical-economic",
        policy_updater=lambda attribution: captured.update(attribution.to_dict()) or {"ok": True},
    )


def _row(*, net_usd: float = 9.0, realized_after_gas_wei: int = 900) -> dict:
    return {
        "transaction_id": "tx-1",
        "receipt_id": "receipt-1",
        "chain": "ethereum",
        "status": "settled",
        "ok": True,
        "decision_id": "decision-1",
        "correlation_id": "corr-1",
        "execution_id": "execution-1",
        "outcome_id": "outcome-1",
        "sizing_id": "sizing-1",
        "settlement_id": "settlement-1",
        "action": "EXECUTE",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "metadata": {
            "latency_ms": 37,
            "realized_profit_after_gas_wei": realized_after_gas_wei,
            "gas_cost_wei": 100,
            "realized_profit_after_gas_usd_micro": int(max(0, realized_after_gas_wei) * 10_000),
            "settled_net_pnl_usd": net_usd,
            "costs": {"gas_cost_usd": 1.0},
            "operator_intent": {"aggression_mode": "balanced"},
            "wealth_goal": {"target_amount": "100000", "timeframe_days": 180},
            "ai_recommendation": {"action": "execute", "confidence": 0.92},
            "capital_engine_state": {"authority_id": "prime-1", "allocatable_wei": 5000},
        },
        "lineage": {
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "execution_id": "execution-1",
            "outcome_id": "outcome-1",
            "sizing_id": "sizing-1",
            "settlement_id": "settlement-1",
            "action": "EXECUTE",
        },
    }


def test_canonical_economic_identity_survives_settlement_and_attribution():
    captured = {}
    result = ingest_settled_ledger_record(_loop(captured), _row())

    assert result["ok"] is True
    lineage = result["lineage"]
    assert lineage["decision_id"] == "decision-1"
    assert lineage["correlation_id"] == "corr-1"
    assert lineage["execution_id"] == "execution-1"
    assert lineage["outcome_id"] == "outcome-1"
    assert lineage["sizing_id"] == "sizing-1"
    assert lineage["settlement_id"] == "settlement-1"
    assert lineage["realized_net_usd"] == 9.0
    assert lineage["net_prediction_error_usd"] == 9.0
    assert lineage["realized_latency_ms"] == 37.0
    assert lineage["capital_engine_state"]["authority_id"] == "prime-1"
    assert lineage["operator_intent"]["aggression_mode"] == "balanced"
    assert lineage["wealth_goal"]["target_amount"] == "100000"
    assert lineage["ai_recommendation"]["confidence"] == 0.92

    assert result["attribution"]["decision_id"] == "decision-1"
    assert result["attribution"]["correlation_id"] == "corr-1"
    assert result["attribution"]["execution_id"] == "execution-1"
    assert result["attribution"]["settlement_id"] == "settlement-1"
    assert result["attribution"]["metadata"]["outcome_id"] == "outcome-1"
    assert result["attribution"]["metadata"]["sizing_id"] == "sizing-1"
    assert captured["decision_id"] == "decision-1"


def test_settled_after_gas_value_is_not_charged_gas_twice():
    captured = {}
    result = ingest_settled_ledger_record(_loop(captured), _row(net_usd=9.0, realized_after_gas_wei=900))

    # The bridge reconstructs pre-gas realized value (900 + 100) because the
    # learning loop subtracts realized_gas_wei exactly once.
    assert result["attribution"]["reward_wei"] == 900
    assert result["attribution"]["metadata"]["gas_accounting"] == "realized_after_gas_plus_gas_minus_gas_once"


def test_successful_cost_only_loss_remains_learning_eligible():
    captured = {}
    result = ingest_settled_ledger_record(_loop(captured), _row(net_usd=-1.0, realized_after_gas_wei=0))

    assert result["ok"] is True
    assert result["eligible_for_learning"] is True
    assert captured["decision_id"] == "decision-1"
