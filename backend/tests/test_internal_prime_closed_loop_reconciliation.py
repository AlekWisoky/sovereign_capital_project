from __future__ import annotations

from typing import Any

from victor_ai_bot.internal_prime.allocator import InternalPrimeAllocator
from victor_ai_bot.internal_prime.contracts import PrimeBorrowRequest
from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService


class _PrimeRuntime:
    def __init__(self, prime: InternalPrimeAllocator):
        self._prime = prime
        self._ledger_repo = prime._ledger_repo
        self._ledger = prime._ledger
        self.cfg = type("Cfg", (), {"chain": type("Chain", (), {"name": prime.chain})()})()
        self._bankroll = type(
            "Bankroll",
            (),
            {
                "state": type("State", (), {"realized_profit_wei": 0, "last_amount_in_wei": 0})(),
                "cfg": type(
                    "Cfg", (), {"auto_reinvest_enabled": False, "reinvest_rate_pct": 0.0}
                )(),
            },
        )()

    def ledger_state(self) -> dict[str, Any]:
        return AuxiliaryStateService().ledger_state(self)

    def internal_prime_state(self) -> dict[str, Any]:
        return self._prime.snapshot()

    def treasury_state(self) -> dict[str, Any]:
        return {"enabled": True}

    def capital_engine_state(self) -> dict[str, Any]:
        return {
            "updated_ts_ms": 4102444800000,
            "capital_engine": {
                "deployable_bankroll_wei": 0,
                "estimated_capital_wei": 0,
                "drawdown_buffer_wei": 0,
                "family_targets": {},
                "updated_ts_ms": 4102444800000,
            },
            "capital_efficiency_metrics": {"updated_ts_ms": 4102444800000},
            "reinvestment_policy": {"updated_ts_ms": 4102444800000},
        }

    def launch_state(self) -> dict[str, Any]:
        return {}


def _request() -> PrimeBorrowRequest:
    return PrimeBorrowRequest(
        family="flash_arb",
        capital_source="internal_prime",
        notional_usd=100000.0,
        asset="USDC",
        horizon_minutes=60.0,
        confidence=0.9,
    )


def _stage_policy() -> dict[str, float]:
    return {
        "max_deployable_pct": 0.5,
        "family_cap_pct": 0.25,
        "prime_capacity_usd": 1_000_000.0,
        "collateral_efficiency": 0.95,
        "min_collateral_ratio": 1.10,
        "collateral_haircut_pct": 5.0,
    }


def test_internal_prime_closed_loop_reconciliation_tracks_dispute_and_final_settlement(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 200000.0)
    opened = prime.allocate(_request(), stage_policy=_stage_policy())
    assert opened["allowed"] is True
    loan_id = opened["loan"]["loan_id"]

    prime.inventory._assets = {}
    prime.inventory._save()
    disputed = prime.settle(loan_id, realized_pnl_usd=25.0)
    assert disputed["ok"] is False
    assert disputed["reason_code"] == "inventory_untracked_on_settlement"

    truth = CapitalTruthService().summary(_PrimeRuntime(prime))
    assert truth["status"] == "ok"
    assert truth["reconciliation"]["internal_prime_journal"]["ok"] is True
    assert truth["reconciliation"]["internal_prime_journal"]["derived"]["disputed_loan_count"] == 1
    assert (
        truth["reconciliation"]["internal_prime_journal"]["derived"]["reserved_collateral_usd"]
        == 115500.0
    )
    assert truth["reconciliation"]["internal_prime_ledger"]["ok"] is True

    prime.inventory.seed("USDC", 0.0)
    settled = prime.settle(loan_id, realized_pnl_usd=25.0)
    assert settled["ok"] is True

    truth_after = CapitalTruthService().summary(_PrimeRuntime(prime))
    assert truth_after["reconciliation"]["internal_prime_journal"]["ok"] is True
    assert truth_after["reconciliation"]["internal_prime_ledger"]["ok"] is True
    assert (
        truth_after["reconciliation"]["internal_prime_journal"]["derived"]["open_loan_count"] == 0
    )
    assert "internal_prime_journal_active_loan_status_mismatch" not in set(
        truth_after["status_reasons"]
    )


def test_internal_prime_closed_loop_reconciliation_degrades_on_state_status_drift(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 200000.0)
    opened = prime.allocate(_request(), stage_policy=_stage_policy())
    assert opened["allowed"] is True
    loan_id = opened["loan"]["loan_id"]

    prime._loans[loan_id]["status"] = "disputed"
    prime._loans[loan_id]["disputed_ts_ms"] = 123456789
    prime._loans[loan_id]["dispute_reason_code"] = "inventory_untracked_on_settlement"
    prime._save_state()

    truth = CapitalTruthService().summary(_PrimeRuntime(prime))
    reasons = set(truth["status_reasons"])
    assert truth["status"] == "degraded"
    assert "internal_prime_journal_active_loan_status_mismatch" in reasons
    assert truth["reconciliation"]["internal_prime_journal"]["loan_deltas"][
        "status_mismatch_ids"
    ] == [loan_id]


def test_internal_prime_closed_loop_reconciliation_stays_clean_after_settlement_persist_rollback(
    tmp_path, monkeypatch
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 200000.0)
    opened = prime.allocate(_request(), stage_policy=_stage_policy())
    assert opened["allowed"] is True
    loan_id = opened["loan"]["loan_id"]

    original_save_state = prime._save_state
    failure_state = {"count": 0}

    def _boom_once() -> None:
        failure_state["count"] += 1
        if failure_state["count"] == 1:
            raise OSError("disk full")
        original_save_state()

    monkeypatch.setattr(prime, "_save_state", _boom_once)
    settled = prime.settle(loan_id, realized_pnl_usd=5.0)
    assert settled == {"ok": False, "reason_code": "prime_settlement_persist_failed"}

    truth = CapitalTruthService().summary(_PrimeRuntime(prime))
    assert truth["reconciliation"]["internal_prime_journal"]["ok"] is True
    assert truth["reconciliation"]["internal_prime_ledger"]["ok"] is True
    assert "internal_prime_journal_unmatched_settlement" not in set(truth["status_reasons"])
