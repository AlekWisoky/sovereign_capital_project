from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.money_loop_accounting import MoneyLoopAccounting
from victor_ai_bot.runtime_services import canonical_capital_write_service as canonical_writer_module
from victor_ai_bot.runtime_services.canonical_capital_write_service import CanonicalCapitalWriteService


def _settlement_tx(*, receipt_id: str, tx_id: str, status: int, net: float) -> dict:
    return {
        "transaction_id": tx_id,
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


def test_money_loop_uses_signed_settled_pnl_not_success_boolean():
    economics = MoneyLoopAccounting.from_ledger_transaction(
        _settlement_tx(receipt_id="r-fail", tx_id="tx-fail", status=0, net=-0.35)
    )
    assert economics.success is False
    assert economics.signed_pnl_usd == -0.35
    assert economics.loss_usd == 0.35
    assert economics.reinvestable_profit_usd == 0.0


def test_bankroll_records_signed_loss_and_blocks_compounding():
    bankroll = BankrollManager(
        BankrollConfig(
            auto_reinvest_enabled=True,
            reinvest_rate_pct=100,
            base_borrow_amount_wei=1_000,
            max_borrow_amount_wei=10_000,
        )
    )
    economics = MoneyLoopAccounting.from_ledger_transaction(
        _settlement_tx(receipt_id="r-fail", tx_id="tx-fail", status=0, net=-0.35)
    )
    bankroll.record_settled_outcome(economics)
    assert bankroll.state.realized_pnl_usd == -0.35
    assert bankroll.state.realized_loss_usd == 0.35
    assert bankroll.state.reinvestable_profit_usd == 0.0
    assert bankroll.state.last_settled_receipt_id == "r-fail"
    assert bankroll.next_amount_in() == 1_000


def test_canonical_writer_projects_bankroll_from_settled_receipt(monkeypatch):
    calls = {}
    real_writer = canonical_writer_module.CapitalWriteService

    def fake_commit(self, runtime, **kwargs):
        calls["bankroll_state"] = dict(runtime._bankroll.project_trade_state(**kwargs))
        return {"ok": True, "ledger_entries": [], "treasury_snapshot": {}}

    monkeypatch.setattr(real_writer, "commit_receipt_settlement", fake_commit)

    bankroll = BankrollManager(BankrollConfig(base_borrow_amount_wei=1_000))
    runtime = SimpleNamespace(_bankroll=bankroll)
    tx = _settlement_tx(receipt_id="r-loss", tx_id="tx-loss", status=0, net=-0.35)
    result = CanonicalCapitalWriteService().commit_receipt_settlement(
        runtime,
        tx_payload=tx,
        tx_lines=[],
        receipt_id="r-loss",
        status=0,
        amount_in=1_000,
        submit_to_receipt_ms=20,
        route_id="route-1",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        realized_after_usd=0.0,
        borrow_cost_usd=0.10,
        net_realized_usd=-0.35,
        gas_cost_wei=1,
        profitability_chain={},
        borrowing={},
        loan_result={},
        outcome_truth_verified=True,
        prime_transition=None,
    )
    assert calls["bankroll_state"]["realized_pnl_usd"] == -0.35
    assert calls["bankroll_state"]["realized_loss_usd"] == 0.35
    assert result["settledEconomics"]["signed_pnl_usd"] == -0.35
