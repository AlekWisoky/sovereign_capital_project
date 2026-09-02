from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar import lifecycle_bridge
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    canonical_settled_outcome,
    install_canonical_settlement_bridge,
    install_canonical_settlement_interface,
)
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


class _Repo:
    def __init__(self, rows):
        self.rows = rows

    def all_transactions(self, *, chain):
        assert chain == "ethereum"
        return list(self.rows)


class _Runtime:
    class _Cfg:
        class _Chain:
            name = "ethereum"

        chain = _Chain()

    cfg = _Cfg()

    def __init__(self, rows):
        self._ledger_repo = _Repo(rows)


def _settlement(**metadata):
    return {
        "transaction_id": "ledger-tx-1",
        "ts_ms": 123,
        "tx_type": "receipt_settlement",
        "receipt_id": "0xabc",
        "metadata": {
            "ok": True,
            "expected_net_usd": 1.25,
            "realized_net_usd": 1.10,
            "gas_cost_usd": 0.15,
            "slippage_bps": 2.0,
            "latency_ms": 80,
            "truth_verified": True,
            "route_id": "route-1",
            **metadata,
        },
    }


def test_canonical_settled_outcome_reads_phase2_ledger_only():
    runtime = _Runtime(
        [
            {
                "transaction_id": "not-settled",
                "ts_ms": 999,
                "tx_type": "trade_submission",
                "receipt_id": "0xabc",
                "metadata": {"realized_net_usd": 999.0},
            },
            _settlement(
                canonical_decision_id="decision-1",
                correlation_id="corr-1",
                opportunity_id="opp-1",
            ),
        ]
    )

    outcome = canonical_settled_outcome(
        runtime,
        tx_hash="0xabc",
        decision_id="decision-1",
        correlation_id="corr-1",
        opportunity_id="opp-1",
    )

    assert outcome is not None
    assert outcome["status"] == "settled"
    assert outcome["source"] == "phase2_canonical_outcome_ledger"
    assert outcome["transaction_id"] == "ledger-tx-1"
    assert outcome["tx_hash"] == "0xabc"
    assert outcome["decision_id"] == "decision-1"
    assert outcome["correlation_id"] == "corr-1"
    assert outcome["realized_net_usd"] == 1.10
    assert outcome["truth_verified"] is True


def test_canonical_settled_outcome_returns_none_without_settlement_transaction():
    runtime = _Runtime(
        [
            {
                "transaction_id": "trade-1",
                "ts_ms": 123,
                "tx_type": "trade_submission",
                "receipt_id": "0xabc",
                "metadata": {"canonical_decision_id": "decision-1"},
            }
        ]
    )

    assert (
        canonical_settled_outcome(runtime, tx_hash="0xabc", decision_id="decision-1")
        is None
    )


def test_runtime_interface_exposes_the_same_canonical_ledger_record():
    install_canonical_settlement_interface()
    runtime = object.__new__(RuntimeReceiptFacade)
    runtime.cfg = _Runtime._Cfg()
    runtime._ledger_repo = _Repo([_settlement(canonical_decision_id="decision-1")])

    outcome = runtime.canonical_settled_outcome(
        tx_hash="0xabc", decision_id="decision-1"
    )

    assert outcome is not None
    assert outcome["source"] == "phase2_canonical_outcome_ledger"
    assert outcome["decision_id"] == "decision-1"


def test_phase4_bridge_uses_runtime_canonical_interface(monkeypatch):
    calls = []

    def canonical_settled_outcome(**kwargs):
        calls.append(kwargs)
        return {
            "status": "settled",
            "realized_net_usd": 2.0,
            "lineage_persisted": True,
        }

    runtime = SimpleNamespace(canonical_settled_outcome=canonical_settled_outcome)
    opp = SimpleNamespace(
        id="opp-1",
        meta={"brain": {"canonical_decision_id": "decision-1", "correlation_id": "corr-1"}},
    )
    result = SimpleNamespace(tx_hash="0xabc")

    install_canonical_settlement_bridge()
    outcome = lifecycle_bridge._canonical_settled_outcome(runtime, result, opp)

    assert outcome["status"] == "settled"
    assert calls == [
        {
            "tx_hash": "0xabc",
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "opportunity_id": "opp-1",
        }
    ]
