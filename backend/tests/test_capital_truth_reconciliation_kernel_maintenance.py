from __future__ import annotations

from victor_ai_bot.runtime_services.capital_truth_reconciliation import (
    build_capital_truth_reconciliation_payload,
)
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService


def test_capital_truth_reconciliation_kernel_converges_internal_prime_and_freshness_truth():
    payload = build_capital_truth_reconciliation_payload(
        treasury_balance_wei=2000,
        deployed_capital_wei=1500,
        withdrawable_balance_wei=200,
        realized_profit_wei=300,
        prime_state_ready=True,
        prime_state_reason="",
        borrowed_usd=125000.0,
        prime_capacity_usd=250000.0,
        prime_utilization=0.5,
        prime_family_exposure={"flash_arb": 125000.0},
        prime_open_loan_count=1,
        reserved_collateral_usd=150000.0,
        collateralization_ratio=1.2,
        prime_journal_reconciliation={"ok": True, "reasons": []},
        prime_ledger_reconciliation={"ok": True, "reasons": []},
        receipt_settlement={
            "ok": True,
            "status": "settled",
            "last_receipt_id": "rcpt-1",
            "last_transaction_id": "tx-1",
            "reason_codes": [],
        },
        receipt_outcome_truth={"updated_ts_ms": 1710000000000},
        receipt_outcome_truth_degraded=False,
        receipt_outcome_truth_reason_code="ok",
        convergence={
            "ok": True,
            "reason_codes": [],
            "freshness_class": "current",
            "freshness_reason_codes": [],
            "reference_ts_ms": 1710000000000,
            "newest_source_ts_ms": 1710000000000,
            "source_spread_ms": 0,
        },
        auto_reinvest=True,
        reinvest_rate_pct=40.0,
        launch_mode="V1_PLUS_STABLE_ALPHA",
        capital_engine_present=True,
        recovery_history={"component": "capital_truth", "degraded_count": 0},
        profit_destination="treasury",
    )

    assert payload["status"] == "ok"
    assert payload["status_reason_code"] == "ok"
    assert payload["freshness"]["class"] == "current"
    assert payload["reconciliation"]["internal_prime_ledger"]["ok"] is True
    assert payload["reconciliation"]["receipt_settlement"]["last_receipt_id"] == "rcpt-1"
    assert payload["withdrawal"]["available"] is True
    assert payload["withdrawal"]["reason_codes"] == ["ok"]


def test_capital_truth_reconciliation_kernel_fails_closed_on_receipt_truth_and_prime_mismatch():
    payload = build_capital_truth_reconciliation_payload(
        treasury_balance_wei=100,
        deployed_capital_wei=200,
        withdrawable_balance_wei=500,
        realized_profit_wei=100,
        prime_state_ready=False,
        prime_state_reason="internal_prime_state_unavailable",
        borrowed_usd=1000.0,
        prime_capacity_usd=500.0,
        prime_utilization=0.1,
        prime_family_exposure={"flash_arb": 1500.0},
        prime_open_loan_count=1,
        reserved_collateral_usd=1200.0,
        collateralization_ratio=1.2,
        prime_journal_reconciliation={
            "ok": False,
            "reasons": ["internal_prime_journal_borrowed_mismatch"],
        },
        prime_ledger_reconciliation={
            "ok": False,
            "reasons": ["internal_prime_ledger_borrowed_mismatch"],
        },
        receipt_settlement={
            "ok": False,
            "status": "unverified",
            "reason_codes": ["settled_profit_truth_unavailable"],
        },
        receipt_outcome_truth={"degraded_count": 3},
        receipt_outcome_truth_degraded=True,
        receipt_outcome_truth_reason_code="settled_profit_truth_unavailable",
        convergence={
            "ok": False,
            "reason_codes": ["ledger_freshness_stale"],
            "freshness_class": "stale",
            "freshness_reason_codes": ["ledger_freshness_stale"],
            "reference_ts_ms": 0,
            "newest_source_ts_ms": 0,
            "source_spread_ms": 0,
        },
        auto_reinvest=False,
        reinvest_rate_pct=0.0,
        launch_mode="V1",
        capital_engine_present=True,
        recovery_history={"component": "capital_truth", "degraded_count": 2},
        profit_destination="treasury",
    )

    assert payload["status"] == "degraded"
    assert payload["status_reason_code"] == "treasury_balance_below_deployable"
    assert "internal_prime_state_unavailable" in payload["reasons"]
    assert "settled_profit_truth_unavailable" in payload["reasons"]
    assert "internal_prime_journal_borrowed_mismatch" in payload["reasons"]
    assert payload["freshness"]["class"] == "stale"
    assert payload["reconciliation"]["ledger_stale"] is True
    assert payload["withdrawal"]["available"] is False
    assert payload["withdrawal"]["previewable"] is True
    assert payload["withdrawal"]["reason_codes"][0] == "treasury_balance_below_deployable"


class _Chain:
    name = "ethereum"


class _Execution:
    profit_to = "treasury"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _BankrollState:
    realized_profit_wei = 500
    last_amount_in_wei = 2000


class _BankrollCfg:
    auto_reinvest_enabled = True
    reinvest_rate_pct = 40.0


class _Bankroll:
    state = _BankrollState()
    cfg = _BankrollCfg()


class _Runtime:
    cfg = _Cfg()
    _bankroll = _Bankroll()

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": 2000,
                "drawdown_buffer_wei": 300,
                "estimated_capital_wei": 2600,
                "family_targets": {"flash_arb": 0.6},
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": 2000},
            "reinvestment_policy": {"reinvestPct": 40.0},
        }

    def treasury_state(self):
        return {"enabled": True}

    def internal_prime_state(self):
        return {
            "borrowedUsd": 0.0,
            "capacityUsd": 1_000_000.0,
            "utilization": 0.0,
            "familyExposure": {},
            "loanCount": 0,
        }

    def ledger_state(self):
        return {
            "balances": {"USDC": 500.0},
            "tail": [{"ts_ms": 4102444800000, "asset": "USDC", "amount": 500.0}],
            "transactions": [],
        }

    def launch_state(self):
        return {"profile": {"mode": "V1_PLUS_STABLE_ALPHA"}}


def test_capital_truth_service_still_emits_canonical_projection_through_reconciliation_kernel():
    truth = CapitalTruthService().summary(_Runtime())

    assert truth["canonical"] is True
    assert truth["read_model"] == "ledgered_capital_truth_v3_converged"
    assert truth["summaryContract"]["readModel"] == "capital_truth_projection_v1"
    assert truth["reconciliation"]["capital_convergence"]["freshness_class"] in {"unknown", "current", "stale", "degraded", "unavailable"}
