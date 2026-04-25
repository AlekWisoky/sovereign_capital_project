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
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
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
            self._db,
            capital_event_repo=self._capital_event_repo,
            chain=self.cfg.chain.name,
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
        self._internal_prime_state_repo = getattr(self._internal_prime, "_state_repo", None)
        self._market_regime = {"regime": "balanced"}

    def treasury_state(self):
        return {"enabled": True}

    def capital_engine_state(self):
        return dict(self._treasury.snapshot() or {})

    def internal_prime_state(self):
        return dict(self._internal_prime.snapshot() or {})

    def launch_state(self):
        return {}

    def ledger_state(self):
        report = self._ledger_repo.transaction_balance_report(chain=self.cfg.chain.name)
        return {
            "balances": dict(report.get("balances") or {}),
            "accountBalances": dict(report.get("accountBalances") or {}),
            "accounting": dict(report.get("accounting") or {}),
            "tail": list(report.get("tail") or []),
            "transactions": self._ledger_repo.transactions_tail(
                chain=self.cfg.chain.name, limit=25
            ),
        }


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


def test_receipt_settlement_produces_shared_capital_commit_lineage(tmp_path):
    runtime = _Runtime(tmp_path)
    loan_id = _allocate_prime(runtime)

    out = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xlineage1",
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
        route_id="route-lineage-1",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )
    assert out["ok"] is True

    receipt_commit = (
        runtime._capital_event_repo.latest_event(domain="receipt").get("payload") or {}
    ).get("capitalCommitId")
    ledger_commit = (
        (runtime._capital_event_repo.latest_event(domain="ledger").get("payload") or {})
        .get("metadata", {})
        .get("capitalCommitId")
    )
    bankroll_commit = (
        runtime._capital_event_repo.latest_event(domain="bankroll").get("payload") or {}
    ).get("capitalCommitId")
    treasury_commit = (
        runtime._capital_event_repo.latest_event(domain="treasury").get("payload") or {}
    ).get("capitalCommitId")
    prime_commit = (
        runtime._capital_event_repo.latest_event(domain="internal_prime").get("payload") or {}
    ).get("capitalCommitId")
    bankroll_history_commit = (
        runtime._bankroll_history_repo.latest_event().get("payload") or {}
    ).get("capitalCommitId")
    treasury_history_commit = (
        runtime._treasury._state_repo.latest(state_type="capital_snapshot").get("payload") or {}
    ).get("capitalCommitId")
    prime_history_commit = (
        runtime._internal_prime._state_repo.latest(state_type="prime_state").get("payload") or {}
    ).get("capitalCommitId")

    assert (
        len(
            {
                commit_id
                for commit_id in [
                    receipt_commit,
                    ledger_commit,
                    bankroll_commit,
                    treasury_commit,
                    prime_commit,
                    bankroll_history_commit,
                    treasury_history_commit,
                    prime_history_commit,
                ]
                if commit_id
            }
        )
        == 1
    )


def test_capital_truth_degrades_when_commit_lineage_drifts(tmp_path):
    runtime = _Runtime(tmp_path)
    loan_id = _allocate_prime(runtime)
    out = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xlineage2",
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
        route_id="route-lineage-2",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )
    assert out["ok"] is True

    latest_treasury = runtime._capital_event_repo.latest_event(domain="treasury")
    broken_payload = dict(latest_treasury.get("payload") or {})
    broken_payload["capitalCommitId"] = "broken-commit"
    runtime._capital_event_repo.append_event(
        ts_ms=int(latest_treasury.get("ts_ms") or 0) + 1,
        domain="treasury",
        event_type=str(latest_treasury.get("event_type") or "capital_snapshot"),
        source=str(latest_treasury.get("source") or "test"),
        transaction_id=str(latest_treasury.get("transaction_id") or ""),
        receipt_id=str(latest_treasury.get("receipt_id") or ""),
        entity_id=str(latest_treasury.get("entity_id") or "treasury_runtime"),
        payload=broken_payload,
    )

    truth = CapitalTruthService().summary(runtime)
    reasons = list(
        (truth.get("reconciliation") or {}).get("capital_convergence", {}).get("reason_codes", [])
        or []
    )
    assert "capital_commit_lineage_mismatch" in reasons
