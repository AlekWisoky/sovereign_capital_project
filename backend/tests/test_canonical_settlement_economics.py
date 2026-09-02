from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.money_loop_accounting import MoneyLoopAccounting
from victor_ai_bot.runtime_services import canonical_capital_write_service as canonical_writer_module
from victor_ai_bot.runtime_services.canonical_capital_write_service import CanonicalCapitalWriteService


def _tx(receipt_id: str, status: int, net: float) -> dict:
    return {
        "transaction_id": f"tx-{receipt_id}",
        "receipt_id": receipt_id,
        "tx_type": "receipt_settlement",
        "metadata": {
            "status": status,
            "amount_in_wei": 1_000,
            "realized_after_gas_wei": 250 if status == 1 else 0,
            "realized_after_gas_usd": 1.25 if status == 1 else 0.0,
            "gas_cost_usd": 0.25,
            "borrow_cost_usd": 0.10,
            "net_realized_usd": net,
        },
    }


def test_settled_receipt_resolves_signed_pnl():
    e = MoneyLoopAccounting.from_ledger_transaction(_tx("loss", 0, -0.35))
    assert e.signed_pnl_usd == -0.35
    assert e.loss_usd == 0.35
    assert e.reinvestable_profit_usd == 0.0


def test_bankroll_signed_loss_controls_reinvestment():
    b = BankrollManager(BankrollConfig(auto_reinvest_enabled=True, reinvest_rate_pct=100, base_borrow_amount_wei=1000, max_borrow_amount_wei=10000))
    b.record_settled_outcome(MoneyLoopAccounting.from_ledger_transaction(_tx("loss", 0, -0.35)))
    assert b.state.realized_pnl_usd == -0.35
    assert b.state.realized_loss_usd == 0.35
    assert b.next_amount_in() == 1000


def test_positive_settled_profit_can_compound():
    b = BankrollManager(BankrollConfig(auto_reinvest_enabled=True, reinvest_rate_pct=100, base_borrow_amount_wei=1000, max_borrow_amount_wei=10000))
    b.record_settled_outcome(MoneyLoopAccounting.from_ledger_transaction(_tx("win", 1, 1.15)))
    assert b.state.realized_pnl_usd == 1.15
    assert b.state.reinvestable_profit_usd == 1.15
    assert b.state.realized_profit_wei == 250
    assert b.next_amount_in() == 1250


def test_canonical_writer_passes_settled_economics_to_bankroll(monkeypatch):
    captured = {}
    def fake_commit(self, runtime, **kwargs):
        captured["state"] = runtime._bankroll.project_trade_state(**kwargs)
        return {"ok": True}
    monkeypatch.setattr(canonical_writer_module.CapitalWriteService, "commit_receipt_settlement", fake_commit)
    runtime = SimpleNamespace(_bankroll=BankrollManager(BankrollConfig(base_borrow_amount_wei=1000)))
    tx = _tx("loss", 0, -0.35)
    out = CanonicalCapitalWriteService().commit_receipt_settlement(
        runtime, tx_payload=tx, tx_lines=[], receipt_id="loss", status=0, amount_in=1000,
        submit_to_receipt_ms=10, route_id="route", route_family="flash_arb", strategy_family="flash_arb",
        capture_lane_pending="private", realized_after_usd=0.0, borrow_cost_usd=0.10, net_realized_usd=-0.35,
        gas_cost_wei=1, profitability_chain={}, borrowing={}, loan_result={}, outcome_truth_verified=True,
        prime_transition=None,
    )
    assert captured["state"]["realized_pnl_usd"] == -0.35
    assert out["settledEconomics"]["signed_pnl_usd"] == -0.35
