from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services import receipt_service as receipt_module
from victor_ai_bot.runtime_services.canonical_receipt_service import CanonicalReceiptService


class _Ledger:
    def transactions_all(self):
        return [
            {
                "transaction_id": "tx-1",
                "receipt_id": "receipt-1",
                "tx_type": "receipt_settlement",
                "metadata": {
                    "status": 0,
                    "amount_in_wei": 1000,
                    "realized_after_gas_usd": 0.0,
                    "gas_cost_usd": 0.25,
                    "borrow_cost_usd": 0.10,
                    "net_realized_usd": -0.35,
                },
            }
        ]


def test_canonical_receipt_learning_enriches_reward_with_signed_pnl(monkeypatch):
    captured = {}

    def fake_update(self, runtime, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(receipt_module.ReceiptService, "update_decision_learning", fake_update)
    runtime = SimpleNamespace(_ledger=_Ledger())
    CanonicalReceiptService().update_decision_learning(
        runtime,
        route_id="route-1",
        rl_state="state-1",
        rl_action=2,
        amount_in=1000,
        expected_after=50,
        realized_after=0,
        status=0,
        tx_hash="receipt-1",
        mode="auto",
        latency_ms=4,
        submit_to_receipt_ms=20,
        aqe_action="EXECUTE",
        pending={"opportunity_id": "opp-1"},
        reward_trace={"reward": -0.1},
    )
    trace = captured["reward_trace"]
    assert trace["settled_net_pnl_usd"] == -0.35
    assert trace["settled_loss_usd"] == 0.35
    assert trace["reinvestable_profit_usd"] == 0.0
    assert trace["settled_receipt_id"] == "receipt-1"
    assert trace["settled_transaction_id"] == "tx-1"
