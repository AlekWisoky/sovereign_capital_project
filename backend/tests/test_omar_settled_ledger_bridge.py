from victor_ai_bot.omar.real_learning import OmarRealLearningLoop
from victor_ai_bot.omar.settled_ledger_bridge import ingest_settled_ledger_record


def test_omar_ingests_complete_settled_ledger_lineage(tmp_path):
    updates = []
    loop = OmarRealLearningLoop(
        chain_name="test",
        data_dir=str(tmp_path),
        capital_authority_reader=lambda: {
            "authority_id": "prime-1",
            "available_wei": 10_000,
            "allocatable_wei": 8_000,
            "status": "authoritative",
            "freshness_class": "fresh",
            "source": "internal_prime",
        },
        policy_updater=lambda attribution: updates.append(attribution.to_dict())
        or {"updated": True},
    )

    result = ingest_settled_ledger_record(
        loop,
        {
            "transaction_id": "tx-1",
            "receipt_id": "0xabc",
            "chain": "ethereum",
            "metadata": {
                "decision_id": "decision-1",
                "correlation_id": "corr-1",
                "execution_id": "exec-1",
                "settlement_id": "settle-1",
                "action": "trade",
                "opportunity_id": "opp-1",
                "route_id": "route-1",
                "policy_version": "policy-1",
                "status": "settled",
                "realized_profit_after_gas_wei": 700,
                "gas_cost_wei": 100,
                "submit_to_receipt_ms": 250,
            },
        },
    )

    assert result["ok"] is True
    assert result["eligible_for_learning"] is True
    assert result["lineage"]["decision_id"] == "decision-1"
    assert result["lineage"]["latency_class"] == "fast"
    assert result["attribution"]["reward_wei"] == 600
    assert updates and updates[0]["decision_id"] == "decision-1"
    assert loop._decisions["decision-1"].capital_authority.authority_id == "prime-1"


def test_omar_refuses_incomplete_settled_lineage(tmp_path):
    loop = OmarRealLearningLoop(chain_name="test", data_dir=str(tmp_path))

    result = ingest_settled_ledger_record(
        loop,
        {
            "transaction_id": "tx-1",
            "metadata": {"status": "settled", "decision_id": "decision-1"},
        },
    )

    assert result["ok"] is False
    assert result["eligible_for_learning"] is False
    assert "missing_correlation_id" in result["reason_codes"]
    assert "missing_execution_id" in result["reason_codes"]
    assert "missing_settlement_id" in result["reason_codes"]
