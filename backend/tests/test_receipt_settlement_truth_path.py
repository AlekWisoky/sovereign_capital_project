from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.command_center_overlay import AuditStore
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.pnl import PnLStore
from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.treasury.ledger import TreasuryLedger


class _Chain:
    name = "ethereum"


class _Execution:
    executor_address = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    profit_to = "0x1111111111111111111111111111111111111111"
    withdraw_mode = "txdata"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _BankrollState:
    realized_profit_wei = 100
    last_amount_in_wei = 1000


class _BankrollCfg:
    auto_reinvest_enabled = False
    reinvest_rate_pct = 0.0


class _Bankroll:
    state = _BankrollState()
    cfg = _BankrollCfg()


class _Runtime:
    cfg = _Cfg()
    _bankroll = _Bankroll()

    def __init__(self, tmp_path):
        self._db = PersistenceDB(str(tmp_path / "state.sqlite3"))
        self._ledger_repo = LedgerRepository(self._db)
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain=self.cfg.chain.name)
        self._pnl = PnLStore(str(tmp_path / "pnl.sqlite3"))
        self._cc = SimpleNamespace(audit=AuditStore(str(tmp_path / "cc_audit_ethereum.jsonl")))

    def treasury_state(self):
        return {"enabled": True}

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": 0,
                "estimated_capital_wei": 0,
                "drawdown_buffer_wei": 0,
                "family_targets": {},
            },
            "capital_efficiency_metrics": {},
            "reinvestment_policy": {},
        }

    def internal_prime_state(self):
        return {
            "borrowedUsd": 0.0,
            "capacityUsd": 1_000_000.0,
            "utilization": 0.0,
            "familyExposure": {},
            "loanCount": 0,
        }

    def launch_state(self):
        return {}

    def ledger_state(self):
        return AuxiliaryStateService().ledger_state(self)


def _seed_trade(runtime: _Runtime, *, tx_hash: str, realized_after: str = "100") -> None:
    async def _seed() -> None:
        await runtime._pnl.init()
        trade_id = await runtime._pnl.add_trade(
            {
                "ts": 1,
                "chain": runtime.cfg.chain.name,
                "opportunity_id": "opp-1",
                "route_id": "route-1",
                "tx_hash": tx_hash,
                "mode": "auto",
                "dry_run": False,
                "ok": True,
                "reason": "submitted",
                "expected_gross_profit_wei": "110",
                "expected_profit_after_costs_wei": realized_after,
                "estimated_gas_cost_wei": "10",
                "flashloan_fee_wei": "1",
                "gas_limit": 21000,
                "max_fee_wei": "1",
                "priority_fee_wei": "1",
                "strategy_type": "flash_arb",
                "income_stream": "arb",
                "venue_path": "uniswap",
            }
        )
        import sqlite3

        con = sqlite3.connect(runtime._pnl.path)
        try:
            con.execute(
                "UPDATE trades SET receipt_status=?, realized_profit_after_gas_wei=?, realized_profit_token=?, realized_profit_token_wei=?, realized_profit_after_gas_usd_micro=? WHERE id=?",
                (
                    1,
                    str(realized_after),
                    "USDC",
                    str(realized_after),
                    str(realized_after),
                    int(trade_id),
                ),
            )
            con.commit()
        finally:
            con.close()

    asyncio.run(_seed())


def test_receipt_service_records_canonical_receipt_settlement_in_ledger_repo(tmp_path):
    runtime = _Runtime(tmp_path)
    svc = ReceiptService()
    out = svc.synchronize_settlement_accounting(
        runtime,
        tx_hash="0xabc",
        pending={"strategy_family": "flash_arb", "route_family": "flash_arb"},
        decoded={
            "realized_profit_after_gas_wei": "100",
            "realized_profit_token": "USDC",
            "realized_profit_token_wei": "100",
            "realized_profit_after_gas_usd_micro": "100",
        },
        status=1,
        amount_in=1000,
        expected_after=100,
        realized_after=100,
        submit_to_receipt_ms=10,
        route_id="route-1",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )
    assert out["ok"] is True
    assert (
        runtime._ledger_repo.has_receipt_transaction(
            chain=runtime.cfg.chain.name,
            receipt_id="0xabc",
            tx_type="receipt_settlement",
        )
        is True
    )


def test_capital_truth_service_reconciles_receipt_settlement_happy_path(tmp_path):
    runtime = _Runtime(tmp_path)
    _seed_trade(runtime, tx_hash="0xabc", realized_after="100")
    runtime._cc.audit.append(
        "withdraw_execute",
        {
            "outcome": "submitted",
            "token": "USDC",
            "amount_wei": "25",
            "tx_hash": "0xw1",
        },
        actor="operator",
        reason="manual_withdraw",
    )
    ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xabc",
        pending={"strategy_family": "flash_arb", "route_family": "flash_arb"},
        decoded={
            "realized_profit_after_gas_wei": "100",
            "realized_profit_token": "USDC",
            "realized_profit_token_wei": "100",
            "realized_profit_after_gas_usd_micro": "100",
        },
        status=1,
        amount_in=1000,
        expected_after=100,
        realized_after=100,
        submit_to_receipt_ms=10,
        route_id="route-1",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )
    truth = CapitalTruthService().summary(runtime)
    receipt_settlement = truth["reconciliation"]["receipt_settlement"]
    assert receipt_settlement["ok"] is True
    assert receipt_settlement["pnl_receipts"]["successful_count"] == 1
    assert receipt_settlement["ledger_receipts"]["count"] == 1
    assert receipt_settlement["executor_balance_snapshot"]["available"] is True
    assert receipt_settlement["withdraw_history"]["count"] == 1


def test_capital_truth_service_degrades_when_receipt_journal_missing(tmp_path):
    runtime = _Runtime(tmp_path)
    _seed_trade(runtime, tx_hash="0xabc", realized_after="100")
    truth = CapitalTruthService().summary(runtime)
    receipt_settlement = truth["reconciliation"]["receipt_settlement"]
    assert receipt_settlement["ok"] is False
    assert "receipt_settlement_journal_missing" in set(receipt_settlement["reason_codes"])
    assert truth["status"] == "degraded"


def test_receipt_service_no_longer_exposes_legacy_receipt_settlement_fallback(tmp_path):
    _ = tmp_path
    assert hasattr(ReceiptService(), "synchronize_settlement_accounting") is True
    assert hasattr(ReceiptService(), "record_money_loop_receipt") is False


class _ExplodingRepo:
    def append_transaction(self, *, chain, payload):
        raise OSError("repo offline")

    def has_receipt_transaction(self, *, chain, receipt_id, tx_type):
        return False


def test_receipt_service_fails_closed_when_repo_persist_fails_after_ledger_write(tmp_path):
    runtime = _Runtime(tmp_path)
    runtime._ledger_repo = _ExplodingRepo()

    out = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xdup",
        pending={"strategy_family": "flash_arb", "route_family": "flash_arb"},
        decoded={
            "realized_profit_after_gas_wei": "100",
            "realized_profit_token": "USDC",
            "realized_profit_token_wei": "100",
            "realized_profit_after_gas_usd_micro": "100",
        },
        status=1,
        amount_in=1000,
        expected_after=100,
        realized_after=100,
        submit_to_receipt_ms=10,
        route_id="route-1",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )

    assert out["ok"] is False
    assert out["reason_code"] == "ledger_sync_failed:OSError"
    assert runtime._last_settlement_sync["reason_code"] == "ledger_sync_failed:OSError"
    ledger_rows = runtime._ledger.transactions_tail(limit=10)
    assert [row["receipt_id"] for row in ledger_rows] == ["0xdup"]
    assert "0xdup" not in getattr(runtime, "_settled_receipts", set())


def test_receipt_service_treats_existing_ledger_receipt_as_duplicate_after_repo_failure(tmp_path):
    runtime = _Runtime(tmp_path)
    runtime._ledger_repo = _ExplodingRepo()
    svc = ReceiptService()

    first = svc.synchronize_settlement_accounting(
        runtime,
        tx_hash="0xdup",
        pending={"strategy_family": "flash_arb", "route_family": "flash_arb"},
        decoded={
            "realized_profit_after_gas_wei": "100",
            "realized_profit_token": "USDC",
            "realized_profit_token_wei": "100",
            "realized_profit_after_gas_usd_micro": "100",
        },
        status=1,
        amount_in=1000,
        expected_after=100,
        realized_after=100,
        submit_to_receipt_ms=10,
        route_id="route-1",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )
    second = svc.synchronize_settlement_accounting(
        runtime,
        tx_hash="0xdup",
        pending={"strategy_family": "flash_arb", "route_family": "flash_arb"},
        decoded={
            "realized_profit_after_gas_wei": "100",
            "realized_profit_token": "USDC",
            "realized_profit_token_wei": "100",
            "realized_profit_after_gas_usd_micro": "100",
        },
        status=1,
        amount_in=1000,
        expected_after=100,
        realized_after=100,
        submit_to_receipt_ms=10,
        route_id="route-1",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )

    assert first["ok"] is False
    assert second["ok"] is True
    assert second["duplicate"] is True
    ledger_rows = runtime._ledger.transactions_tail(limit=10)
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["receipt_id"] == "0xdup"
