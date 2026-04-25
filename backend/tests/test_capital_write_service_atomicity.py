from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.command_center_overlay import AuditStore
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.bankroll_repository import BankrollEventRepository
from victor_ai_bot.persistence.repositories.capital_event_repository import CapitalEventRepository
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.runtime_services.capital_write_service import CapitalWriteService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.treasury.config import TreasuryConfig
from victor_ai_bot.treasury.ledger import TreasuryLedger
from victor_ai_bot.treasury.runtime import TreasuryRuntime


class _Chain:
    name = "ethereum"


class _Execution:
    executor_address = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    profit_to = "0x1111111111111111111111111111111111111111"
    withdraw_mode = "txdata"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _CapitalWriteRuntime:
    cfg = _Cfg()

    def __init__(self, tmp_path):
        self._db = PersistenceDB(str(tmp_path / "state.sqlite3"))
        self._capital_event_repo = CapitalEventRepository(self._db, chain=self.cfg.chain.name)
        self._ledger_repo = LedgerRepository(
            self._db, capital_event_repo=self._capital_event_repo, chain=self.cfg.chain.name
        )
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain=self.cfg.chain.name)
        self._cc = SimpleNamespace(audit=AuditStore(str(tmp_path / "cc_audit_ethereum.jsonl")))
        self._bankroll_history_repo = BankrollEventRepository(self._db, chain=self.cfg.chain.name)
        self._bankroll = BankrollManager(
            BankrollConfig(base_borrow_amount_wei=100, max_borrow_amount_wei=500),
            state_path=str(tmp_path / "bankroll_state.json"),
            history_repo=self._bankroll_history_repo,
            capital_event_repo=self._capital_event_repo,
        )
        self._treasury = TreasuryRuntime(
            cfg=TreasuryConfig(enabled=True),
            data_dir=str(tmp_path),
            db=self._db,
            chain=self.cfg.chain.name,
            capital_event_repo=self._capital_event_repo,
        )
        self._capital_write_service = CapitalWriteService()
        self._market_regime = {"regime": "balanced"}


def test_capital_write_service_commits_once_and_prevents_double_bankroll_mutation(tmp_path):
    runtime = _CapitalWriteRuntime(tmp_path)
    service = ReceiptService()
    service.record_trade_outcome(
        runtime,
        status=1,
        realized_after=100,
        expected_after=100,
        amount_in=1000,
        latency_ms=5,
        mode="auto",
        outcome_truth_ok=True,
        outcome_truth_reason_code="ok",
    )
    assert runtime._bankroll.state.realized_profit_wei == 0
    out = service.synchronize_settlement_accounting(
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
    assert runtime._bankroll.state.realized_profit_wei == 100
    assert runtime._ledger_repo.has_receipt_transaction(chain="ethereum", receipt_id="0xabc")
    assert runtime._capital_event_repo.latest_event(domain="ledger")["receipt_id"] == "0xabc"
    assert runtime._capital_event_repo.latest_event(domain="receipt")["receipt_id"] == "0xabc"
    assert runtime._capital_event_repo.latest_event(domain="bankroll")["receipt_id"] == "0xabc"
    assert (
        runtime._capital_event_repo.latest_event(domain="treasury")["event_type"]
        == "capital_snapshot"
    )
    assert runtime._bankroll_history_repo.latest_event()["event_type"] == "trade_recorded"

    receipt_commit_id = (
        runtime._capital_event_repo.latest_event(domain="receipt").get("payload") or {}
    ).get("capitalCommitId")
    ledger_commit_id = (
        (runtime._capital_event_repo.latest_event(domain="ledger").get("payload") or {})
        .get("metadata", {})
        .get("capitalCommitId")
    )
    bankroll_commit_id = (
        runtime._capital_event_repo.latest_event(domain="bankroll").get("payload") or {}
    ).get("capitalCommitId")
    treasury_commit_id = (
        runtime._capital_event_repo.latest_event(domain="treasury").get("payload") or {}
    ).get("capitalCommitId")
    bankroll_history_commit_id = (
        runtime._bankroll_history_repo.latest_event().get("payload") or {}
    ).get("capitalCommitId")
    assert (
        len(
            {
                commit_id
                for commit_id in [
                    receipt_commit_id,
                    ledger_commit_id,
                    bankroll_commit_id,
                    treasury_commit_id,
                    bankroll_history_commit_id,
                ]
                if commit_id
            }
        )
        == 1
    )


def test_capital_write_service_rolls_back_on_midstream_publication_failure(tmp_path, monkeypatch):
    runtime = _CapitalWriteRuntime(tmp_path)
    service = ReceiptService()
    original_append = runtime._capital_event_repo.append_event

    def _flaky_append_event(*, domain, **kwargs):
        if str(domain) == "treasury":
            raise RuntimeError("boom")
        return original_append(domain=domain, **kwargs)

    monkeypatch.setattr(runtime._capital_event_repo, "append_event", _flaky_append_event)
    out = service.synchronize_settlement_accounting(
        runtime,
        tx_hash="0xdef",
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
        route_id="route-2",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )
    assert out["ok"] is False
    assert "capital_write_failed:RuntimeError" in str(out.get("reason") or "")
    assert not runtime._ledger_repo.has_receipt_transaction(chain="ethereum", receipt_id="0xdef")
    assert runtime._bankroll.state.realized_profit_wei == 0
    assert runtime._capital_event_repo.latest_event(domain="receipt") == {}
    assert runtime._bankroll_history_repo.latest_event()["event_type"] != "trade_recorded"
