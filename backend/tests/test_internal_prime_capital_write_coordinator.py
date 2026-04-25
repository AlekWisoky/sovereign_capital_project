from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.command_center_overlay import AuditStore
from victor_ai_bot.internal_prime.allocator import InternalPrimeAllocator
from victor_ai_bot.internal_prime.contracts import PrimeBorrowRequest
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


class _Runtime:
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
        self._internal_prime = InternalPrimeAllocator(
            data_dir=str(tmp_path),
            chain=self.cfg.chain.name,
            db=self._db,
            capital_event_repo=self._capital_event_repo,
            capital_write_service=self._capital_write_service,
        )
        self._internal_prime.inventory.seed("USDC", 500000.0)
        self._market_regime = {"regime": "balanced"}


def _allocate_prime(runtime: _Runtime) -> str:
    out = runtime._internal_prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.95,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 1_000_000.0,
        },
    )
    assert out["allowed"] is True
    return str(out["loan"]["loan_id"])


def test_internal_prime_settlement_flows_through_capital_write_coordinator(tmp_path):
    runtime = _Runtime(tmp_path)
    loan_id = _allocate_prime(runtime)

    out = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xprime1",
        pending={
            "strategy_family": "flash_arb",
            "route_family": "flash_arb",
            "loan_id": loan_id,
        },
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
        route_id="route-prime-1",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )
    assert out["ok"] is True
    assert runtime._ledger_repo.has_receipt_transaction(
        chain="ethereum", receipt_id="0xprime1", tx_type="receipt_settlement"
    )
    tx_tail = runtime._ledger_repo.transactions_tail(chain="ethereum", limit=10)
    tx_types = [str(row.get("tx_type") or "") for row in tx_tail]
    assert "prime_loan_settlement" in tx_types
    assert (
        runtime._capital_event_repo.latest_event(domain="internal_prime")["receipt_id"]
        == "0xprime1"
    )
    latest_prime_state = runtime._internal_prime._state_repo.latest(state_type="prime_state")
    assert latest_prime_state["payload"]["loanCount"] == 0
    assert runtime._internal_prime.snapshot()["loanCount"] == 0
    assert runtime._internal_prime.inventory.snapshot()["USDC"] == 500000.0

    receipt_commit_id = (
        runtime._capital_event_repo.latest_event(domain="receipt").get("payload") or {}
    ).get("capitalCommitId")
    prime_event_commit_id = (
        runtime._capital_event_repo.latest_event(domain="internal_prime").get("payload") or {}
    ).get("capitalCommitId")
    prime_state_commit_id = (latest_prime_state.get("payload") or {}).get("capitalCommitId")
    assert (
        len(
            {
                commit_id
                for commit_id in [receipt_commit_id, prime_event_commit_id, prime_state_commit_id]
                if commit_id
            }
        )
        == 1
    )


def test_internal_prime_settlement_rolls_back_with_receipt_when_coordinator_fails(
    tmp_path, monkeypatch
):
    runtime = _Runtime(tmp_path)
    loan_id = _allocate_prime(runtime)
    original_append = runtime._capital_event_repo.append_event

    def _flaky_append_event(*, domain, **kwargs):
        if str(domain) == "internal_prime":
            raise RuntimeError("boom")
        return original_append(domain=domain, **kwargs)

    monkeypatch.setattr(runtime._capital_event_repo, "append_event", _flaky_append_event)
    out = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xprime2",
        pending={
            "strategy_family": "flash_arb",
            "route_family": "flash_arb",
            "loan_id": loan_id,
        },
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
        route_id="route-prime-2",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )
    assert out["ok"] is False
    assert "capital_write_failed:RuntimeError" in str(out.get("reason") or "")
    assert not runtime._ledger_repo.has_receipt_transaction(
        chain="ethereum", receipt_id="0xprime2", tx_type="receipt_settlement"
    )
    tx_tail = runtime._ledger_repo.transactions_tail(chain="ethereum", limit=10)
    assert all(str(row.get("tx_type") or "") != "prime_loan_settlement" for row in tx_tail)
    assert runtime._internal_prime.snapshot()["loanCount"] == 1
    latest_prime_state = runtime._internal_prime._state_repo.latest(state_type="prime_state")
    assert latest_prime_state["payload"]["loanCount"] == 1
    assert (
        runtime._capital_event_repo.latest_event(domain="receipt").get("receipt_id") != "0xprime2"
    )


def test_internal_prime_open_flows_through_capital_write_coordinator(tmp_path):
    runtime = _Runtime(tmp_path)

    out = runtime._internal_prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.95,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 1_000_000.0,
        },
    )

    assert out["allowed"] is True
    loan_id = str(out["loan"]["loan_id"])
    tx_tail = runtime._ledger_repo.transactions_tail(chain="ethereum", limit=10)
    assert any(str(row.get("tx_type") or "") == "prime_loan_open" for row in tx_tail)
    latest_prime_state = runtime._internal_prime._state_repo.latest(state_type="prime_state")
    assert latest_prime_state["payload"]["loanCount"] == 1
    assert latest_prime_state["payload"]["openLoans"][0]["loan_id"] == loan_id
    assert runtime._internal_prime.inventory.snapshot()["USDC"] == 400000.0
    latest_event = runtime._capital_event_repo.latest_event(domain="internal_prime")
    assert latest_event["event_type"] == "prime_state"
    assert latest_event["entity_id"] == loan_id
    ledger_commit_id = (
        runtime._ledger_repo.transactions_tail(chain="ethereum", limit=1)[0].get("metadata") or {}
    ).get("capitalCommitId")
    prime_event_commit_id = (latest_event.get("payload") or {}).get("capitalCommitId")
    prime_state_commit_id = (latest_prime_state.get("payload") or {}).get("capitalCommitId")
    assert (
        len(
            {
                commit_id
                for commit_id in [ledger_commit_id, prime_event_commit_id, prime_state_commit_id]
                if commit_id
            }
        )
        == 1
    )


def test_internal_prime_open_rolls_back_when_coordinator_fails(tmp_path, monkeypatch):
    runtime = _Runtime(tmp_path)
    original_append = runtime._capital_event_repo.append_event

    def _flaky_append_event(*, domain, event_type, **kwargs):
        if str(domain) == "internal_prime" and str(event_type) == "prime_state":
            raise RuntimeError("boom")
        return original_append(domain=domain, event_type=event_type, **kwargs)

    monkeypatch.setattr(runtime._capital_event_repo, "append_event", _flaky_append_event)

    out = runtime._internal_prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.95,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 1_000_000.0,
        },
    )

    assert out["allowed"] is False
    assert out["reason"] == "prime_open_commit_failed"
    tx_tail = runtime._ledger_repo.transactions_tail(chain="ethereum", limit=10)
    assert all(str(row.get("tx_type") or "") != "prime_loan_open" for row in tx_tail)
    assert runtime._internal_prime.snapshot()["loanCount"] == 0
    assert runtime._internal_prime.inventory.snapshot()["USDC"] == 500000.0
    assert runtime._internal_prime._state_repo.latest(state_type="prime_state") == {}
