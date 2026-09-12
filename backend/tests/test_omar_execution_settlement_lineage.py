from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import attach_execution_identity, create_execution_identity
from victor_ai_bot.runtime_services.canonical_capital_write_service import CanonicalCapitalWriteService
from victor_ai_bot.runtime_services.canonical_settlement_interface import canonical_settled_outcome


def test_execution_identity_is_created_at_execution_boundary_and_preserves_sizing():
    decision = SimpleNamespace(
        metadata={
            "canonical_decision_id": "decision-b3",
            "correlation_id": "corr-b3",
            "sizing_id": "sizing-b3",
        }
    )
    opp = SimpleNamespace(
        id="opp-b3",
        route_id="route-b3",
        meta={
            "brain": {
                "canonical_decision_id": "decision-b3",
                "correlation_id": "corr-b3",
                "sizing_id": "sizing-b3",
            },
            "canonical_lineage": {
                "decision_id": "decision-b3",
                "correlation_id": "corr-b3",
                "sizing_id": "sizing-b3",
            },
        },
    )
    identity = create_execution_identity(decision, opp)
    result = SimpleNamespace(plan={})
    attach_execution_identity(identity, decision=decision, opp=opp, result=result)

    assert identity.execution_id.startswith("execution_")
    assert decision.metadata["execution_id"] == identity.execution_id
    assert opp.meta["canonical_lineage"]["execution_id"] == identity.execution_id
    assert opp.meta["canonical_lineage"]["sizing_id"] == "sizing-b3"
    assert opp.meta["pending_context"]["execution_lineage"]["execution_id"] == identity.execution_id
    assert result.plan["execution_lineage"] == {
        "decision_id": "decision-b3",
        "correlation_id": "corr-b3",
        "execution_id": identity.execution_id,
        "sizing_id": "sizing-b3",
    }


def test_canonical_capital_writer_persists_complete_lineage_and_idempotent_outcome_id():
    runtime = SimpleNamespace(
        _canonical_settlement_lineage={
            "decision_id": "decision-b3",
            "correlation_id": "corr-b3",
            "sizing_id": "sizing-b3",
            "execution_id": "execution-b3",
            "opportunity_id": "opp-b3",
            "route_id": "route-b3",
            "action": "EXECUTE",
            "expected_net_usd": 12.5,
            "capital_demand": {"requested_usd_micro": 1000000, "authorized_usd_micro": 900000},
            "capital_authority": {"authority_id": "prime-b3", "status": "authorized"},
            "internal_prime_authority": {"authority_id": "prime-b3", "available": True},
            "prime_economics": {"borrow_cost_usd": 0.4},
            "latency_ms": 81,
            "slippage_bps": 2.5,
        }
    )
    payload = CanonicalCapitalWriteService()._annotate_settlement_payload(
        runtime,
        {
            "transaction_id": "ledger-b3",
            "metadata": {"gas_cost_usd": 0.2},
        },
        receipt_id="0xreceipt-b3",
        status=1,
        amount_in=500,
        submit_to_receipt_ms=81,
        route_id="route-b3",
        gas_cost_wei=123,
        realized_after_usd=13.1,
        net_realized_usd=12.5,
        borrowing={"provider": "prime", "flashloanFeeWei": 7},
        outcome_truth_verified=True,
    )
    metadata = payload["metadata"]
    lineage = metadata["canonical_lineage"]

    assert lineage == {
        "decision_id": "decision-b3",
        "correlation_id": "corr-b3",
        "sizing_id": "sizing-b3",
        "execution_id": "execution-b3",
        "receipt_id": "0xreceipt-b3",
        "outcome_id": lineage["outcome_id"],
        "opportunity_id": "opp-b3",
        "route_id": "route-b3",
        "action": "EXECUTE",
    }
    assert lineage["outcome_id"].startswith("outcome_")
    assert metadata["decision_id"] == "decision-b3"
    assert metadata["execution_id"] == "execution-b3"
    assert metadata["sizing_id"] == "sizing-b3"
    assert metadata["receipt_id"] == "0xreceipt-b3"
    assert metadata["capital_demand"]["authorized_usd_micro"] == 900000
    assert metadata["internal_prime_authority"]["authority_id"] == "prime-b3"
    assert metadata["settlement_verified"] is True

    second = CanonicalCapitalWriteService()._annotate_settlement_payload(
        runtime,
        {"metadata": {}},
        receipt_id="0xreceipt-b3",
        status=1,
        amount_in=500,
        submit_to_receipt_ms=81,
        route_id="route-b3",
        gas_cost_wei=123,
        realized_after_usd=13.1,
        net_realized_usd=12.5,
        borrowing={"provider": "prime"},
        outcome_truth_verified=True,
    )
    assert second["metadata"]["outcome_id"] == metadata["outcome_id"]


def test_canonical_settlement_reader_requires_exact_execution_identity():
    class LedgerRepo:
        def all_transactions(self, *, chain):
            assert chain == "ethereum"
            return [
                {
                    "tx_type": "receipt_settlement",
                    "transaction_id": "ledger-b3",
                    "receipt_id": "0xreceipt-b3",
                    "ts_ms": 1234,
                    "metadata": {
                        "canonical_decision_id": "decision-b3",
                        "correlation_id": "corr-b3",
                        "sizing_id": "sizing-b3",
                        "execution_id": "execution-b3",
                        "receipt_id": "0xreceipt-b3",
                        "outcome_id": "outcome-b3",
                        "opportunity_id": "opp-b3",
                        "route_id": "route-b3",
                        "action": "EXECUTE",
                        "expected_net_usd": 12.5,
                        "realized_net_usd": 12.5,
                        "gas_cost_usd": 0.2,
                        "slippage_bps": 2.5,
                        "latency_ms": 81,
                        "settlement_verified": True,
                        "truth_verified": True,
                        "capital_demand": {"authorized_usd_micro": 900000},
                        "internal_prime_authority": {"authority_id": "prime-b3"},
                    },
                }
            ]

    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _ledger_repo=LedgerRepo(),
    )
    outcome = canonical_settled_outcome(
        runtime,
        tx_hash="0xreceipt-b3",
        decision_id="decision-b3",
        correlation_id="corr-b3",
        opportunity_id="opp-b3",
        execution_id="execution-b3",
    )
    assert outcome is not None
    assert outcome["canonical_lineage"]["execution_id"] == "execution-b3"
    assert outcome["canonical_lineage"]["sizing_id"] == "sizing-b3"
    assert outcome["canonical_lineage"]["outcome_id"] == "outcome-b3"
    assert outcome["capital_demand"]["authorized_usd_micro"] == 900000

    mismatch = canonical_settled_outcome(
        runtime,
        tx_hash="0xreceipt-b3",
        decision_id="decision-b3",
        correlation_id="corr-b3",
        opportunity_id="opp-b3",
        execution_id="execution-replacement",
    )
    assert mismatch is None
