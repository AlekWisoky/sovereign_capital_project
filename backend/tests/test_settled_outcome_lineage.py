from victor_ai_bot.runtime_services.settled_outcome_lineage import (
    attach_settled_lineage,
    latency_class,
    resolve_settled_lineage,
)


def test_resolve_complete_settled_lineage_and_latency():
    row = {
        "transaction_id": "tx_abc",
        "receipt_id": "0xreceipt",
        "chain": "ethereum",
        "tx_type": "receipt_settlement",
        "metadata": {
            "decision_id": "decision_123",
            "correlation_id": "corr_123",
            "execution_id": "exec_123",
            "settlement_id": "settle_123",
            "action": "trade",
            "opportunity_id": "opp_123",
            "route_id": "route_123",
            "policy_version": "policy_v4",
            "submit_to_receipt_ms": 312,
            "status": "settled",
        },
    }

    lineage = resolve_settled_lineage(row)

    assert lineage.complete is True
    assert lineage.decision_id == "decision_123"
    assert lineage.correlation_id == "corr_123"
    assert lineage.execution_id == "exec_123"
    assert lineage.settlement_id == "settle_123"
    assert lineage.transaction_id == "tx_abc"
    assert lineage.receipt_id == "0xreceipt"
    assert lineage.latency_ms == 312
    assert lineage.latency_class == "fast"


def test_missing_lineage_is_explicitly_incomplete():
    lineage = resolve_settled_lineage(
        {"transaction_id": "tx_only", "metadata": {"status": "settled"}}
    )

    assert lineage.complete is False
    assert "missing_decision_id" in lineage.reason_codes
    assert "missing_correlation_id" in lineage.reason_codes
    assert "missing_execution_id" in lineage.reason_codes
    assert "missing_settlement_id" in lineage.reason_codes


def test_attach_preserves_existing_payload_and_exposes_canonical_ids():
    enriched = attach_settled_lineage(
        {
            "transaction_id": "tx_1",
            "metadata": {
                "decisionId": "decision_1",
                "correlationId": "corr_1",
                "executionId": "exec_1",
                "settlementId": "settle_1",
                "latency_stages_ms": {"total": 1200},
            },
        }
    )

    assert enriched["decision_id"] == "decision_1"
    assert enriched["correlation_id"] == "corr_1"
    assert enriched["execution_id"] == "exec_1"
    assert enriched["settlement_id"] == "settle_1"
    assert enriched["latency_ms"] == 1200
    assert enriched["latency_class"] == "slow"
    assert enriched["lineage"]["complete"] is True


def test_latency_class_boundaries():
    assert latency_class(450) == "fast"
    assert latency_class(450.1) == "moderate"
    assert latency_class(900) == "moderate"
    assert latency_class(900.1) == "slow"
