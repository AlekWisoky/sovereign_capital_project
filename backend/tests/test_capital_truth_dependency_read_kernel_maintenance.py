from __future__ import annotations

from victor_ai_bot.runtime_services.capital_truth_dependency_reads import (
    build_capital_truth_dependency_reads,
)
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService


class _LedgerRepo:
    def all_transactions(self, chain: str):
        assert chain == "base"
        return [
            {"ts_ms": 1_700_000_000_200, "tx_type": "prime_loan_open", "receipt_id": "loan-1"},
            {"ts_ms": 1_700_000_000_300, "tx_type": "withdraw_execute", "receipt_id": "wd-1"},
        ]

    def transaction_balance_report(self, chain: str):
        assert chain == "base"
        return {
            "accountBalances": {"internal_prime:borrowed_usd": {"USD": 12500.0}},
            "accounting": {"encumberedAssets": {"USDC": 12500.0}},
        }


class _BankrollHistoryRepo:
    def latest_event(self):
        return {"ts_ms": 1_700_000_000_050, "event_type": "bankroll_commit"}


class _TreasuryStateRepo:
    def latest(self, state_type: str):
        return {"ts_ms": 1_700_000_000_075, "state_type": state_type, "payload": {"updated_ts_ms": 1_700_000_000_075}}


class _PrimeStateRepo:
    def latest(self, state_type: str):
        return {"ts_ms": 1_700_000_000_100, "state_type": state_type, "payload": {"updatedTsMs": 1_700_000_000_100}}


class _CapitalEventRepo:
    def latest_event(self, domain: str):
        return {"ts_ms": 1_700_000_000_125, "event_type": domain, "payload": {"domain": domain}}


class _Audit:
    def tail(self, limit: int = 2000):
        return []


class _CC:
    audit = _Audit()


class _BankrollState:
    realized_profit_wei = 5 * 10**18
    last_amount_in_wei = 25 * 10**18
    success_streak = 3
    fail_streak = 0
    updated_ts_ms = 1_700_000_000_010
    profit_updated_ts_ms = 1_700_000_000_020
    sizing_updated_ts_ms = 1_700_000_000_030


class _BankrollCfg:
    auto_reinvest_enabled = True
    reinvest_rate_pct = 40.0


class _Bankroll:
    state = _BankrollState()
    cfg = _BankrollCfg()


class _ChainCfg:
    name = "base"


class _ExecutionCfg:
    executor_address = "0xexecutor"
    profit_to = "bankroll"


class _Cfg:
    chain = _ChainCfg()
    execution = _ExecutionCfg()


class _Treasury:
    _state_repo = _TreasuryStateRepo()


class _Prime:
    _state_repo = _PrimeStateRepo()


class _RecoveryRepo:
    def load(self, component: str):
        return {"component": component, "degraded_count": 0}

    def observe(self, component: str, degraded: bool, ts_ms: int, reason_code: str):
        return {
            "component": component,
            "degraded_count": 1 if degraded else 0,
            "last_reason_code": reason_code,
            "last_ts_ms": ts_ms,
        }


class _Runtime:
    cfg = _Cfg()
    _ledger_repo = _LedgerRepo()
    _bankroll_history_repo = _BankrollHistoryRepo()
    _treasury = _Treasury()
    _internal_prime = _Prime()
    _capital_event_repo = _CapitalEventRepo()
    _capital_recovery_repo = _RecoveryRepo()
    _bankroll = _Bankroll()
    _cc = _CC()

    def treasury_state(self):
        return {"drawdown_buffer_wei": 5 * 10**18}

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "updated_ts_ms": 1_700_000_000_040,
                "deployable_bankroll_wei": 25 * 10**18,
                "estimated_capital_wei": 30 * 10**18,
                "drawdown_buffer_wei": 5 * 10**18,
                "family_targets": {"flash_arb": 0.7},
                "family_allocations_wei": {"flashloan_atomic": 12 * 10**18},
            },
            "capital_efficiency_metrics": {"updated_ts_ms": 1_700_000_000_035},
            "reinvestment_policy": {"updated_ts_ms": 1_700_000_000_038, "reinvest_pct": 40.0},
        }

    def internal_prime_state(self):
        return {
            "stateReady": True,
            "borrowedUsd": 12500.0,
            "capacityUsd": 250000.0,
            "utilization": 0.05,
            "familyExposure": {"flash_arb": 12500.0},
            "loanCount": 1,
            "openLoans": [{"asset": "USDC", "notional_usd": 12500.0, "openedTsMs": 1_700_000_000_090}],
        }

    def ledger_state(self):
        return {
            "tail": [{"ts_ms": 1_700_000_000_180, "tx_type": "receipt_settlement", "receipt_id": "0xabc"}],
            "balances": {"USDC": 500.0},
        }

    def launch_state(self):
        return {"profile": {"mode": "V1_PLUS_STABLE_ALPHA"}}


class _RuntimeNoRepos(_Runtime):
    _ledger_repo = None
    _bankroll_history_repo = None
    _capital_event_repo = None
    _treasury = type("TNoRepo", (), {"_state_repo": None})()
    _internal_prime = type("PNoRepo", (), {"_state_repo": None})()



def test_capital_truth_dependency_read_kernel_reads_runtime_source_repos() -> None:
    bundle = build_capital_truth_dependency_reads(_Runtime())

    assert bundle.ledger_tail[-1]["receipt_id"] == "0xabc"
    assert bundle.ledger_account_balances["internal_prime:borrowed_usd"]["USD"] == 12500.0
    assert bundle.ledger_accounting["encumberedAssets"]["USDC"] == 12500.0
    assert bundle.ledger_transactions[0]["tx_type"] == "prime_loan_open"
    assert bundle.bankroll_history_enabled is True
    assert bundle.treasury_history_enabled is True
    assert bundle.internal_prime_history_enabled is True
    assert bundle.capital_event_enabled is True
    assert bundle.capital_event_receipt["event_type"] == "receipt"



def test_capital_truth_service_still_emits_canonical_projection_through_dependency_read_kernel(monkeypatch) -> None:
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: 1_700_000_000.5,
    )

    truth = CapitalTruthService().summary(_Runtime())

    assert truth["canonical"] is True
    assert truth["read_model"] == "ledgered_capital_truth_v3_converged"
    assert truth["summaryContract"]["readModel"] == "capital_truth_projection_v1"
    assert truth["reconciliation"]["capital_convergence"]["sources"]["capital_event_receipt"]["available"] is True
    assert truth["reconciliation"]["capital_convergence"]["sources"]["bankroll_history"]["available"] is True



def test_capital_truth_dependency_read_kernel_fails_closed_when_repo_sources_are_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: 1_700_000_000.5,
    )

    truth = CapitalTruthService().summary(_RuntimeNoRepos())

    sources = truth["reconciliation"]["capital_convergence"]["sources"]
    assert sources["bankroll_history"]["material"] is False
    assert sources["bankroll_history"]["freshness_class"] == "idle"
    assert sources["capital_event_receipt"]["material"] is False
    assert sources["capital_event_receipt"]["freshness_class"] == "idle"
    assert truth["status"] == "degraded"
