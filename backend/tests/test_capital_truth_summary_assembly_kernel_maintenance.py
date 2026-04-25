from __future__ import annotations

from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.runtime_services.capital_truth_summary_assembly import (
    build_capital_truth_summary_assembly,
)


class _LedgerRepo:
    def all_transactions(self, chain: str):
        assert chain == "base"
        return [
            {"ts_ms": 1_700_000_000_200, "tx_type": "prime_loan_open", "receipt_id": "loan-1"},
            {
                "ts_ms": 1_700_000_000_500,
                "tx_type": "receipt_settlement",
                "receipt_id": "0xabc",
                "metadata": {
                    "tx_hash": "0xabc",
                    "realized_profit_after_gas_wei": str(5 * 10**18),
                    "realized_profit_token": "WETH",
                    "realized_profit_token_wei": str(5 * 10**18),
                    "realized_profit_after_gas_usd_micro": str(12_500_000),
                },
            },
        ]

    def transaction_balance_report(self, chain: str):
        assert chain == "base"
        return {
            "accountBalances": {"internal_prime:borrowed_usd": {"USD": 12_500.0}},
            "accounting": {
                "encumberedAssets": {"USDC": 12_500.0},
                "assetAccounts": {"asset:executor": {"USDC": 12_500.0}},
            },
        }


class _BankrollHistoryRepo:
    def latest_event(self):
        return {
            "ts_ms": 1_700_000_000_050,
            "event_type": "bankroll_commit",
            "state": {
                "realized_profit_wei": 5 * 10**18,
                "last_amount_in_wei": 25 * 10**18,
                "success_streak": 3,
                "fail_streak": 0,
                "updated_ts_ms": 1_700_000_000_010,
                "profit_updated_ts_ms": 1_700_000_000_020,
                "sizing_updated_ts_ms": 1_700_000_000_030,
            },
            "capitalCommitId": "commit-assembly-1",
        }


class _TreasuryStateRepo:
    def latest(self, state_type: str):
        return {
            "ts_ms": 1_700_000_000_075,
            "state_type": state_type,
            "payload": {
                "updated_ts_ms": 1_700_000_000_075,
                "capital_engine": {
                    "updated_ts_ms": 1_700_000_000_040,
                    "deployable_bankroll_wei": 25 * 10**18,
                    "estimated_capital_wei": 30 * 10**18,
                    "drawdown_buffer_wei": 5 * 10**18,
                    "family_allocations_wei": {"flashloan_atomic": 12 * 10**18},
                },
                "capitalCommitId": "commit-assembly-1",
            },
        }


class _PrimeStateRepo:
    def latest(self, state_type: str):
        return {
            "ts_ms": 1_700_000_000_100,
            "state_type": state_type,
            "payload": {"updatedTsMs": 1_700_000_000_100, "capitalCommitId": "commit-assembly-1"},
        }


class _CapitalEventRepo:
    def latest_event(self, domain: str):
        mapping = {
            "bankroll": {"ts_ms": 1_700_000_000_080, "event_type": "bankroll", "payload": {"capitalCommitId": "commit-assembly-1", "state": {"updated_ts_ms": 1_700_000_000_080}}},
            "treasury": {"ts_ms": 1_700_000_000_090, "event_type": "treasury", "payload": {"capitalCommitId": "commit-assembly-1", "capital_engine": {"updated_ts_ms": 1_700_000_000_090, "deployable_bankroll_wei": 25 * 10**18, "estimated_capital_wei": 30 * 10**18, "drawdown_buffer_wei": 5 * 10**18, "family_allocations_wei": {"flashloan_atomic": 12 * 10**18}}}},
            "ledger": {"ts_ms": 1_700_000_000_200, "event_type": "ledger", "payload": {"capitalCommitId": "commit-assembly-1", "tx_type": "receipt_settlement"}},
            "receipt": {"ts_ms": 1_700_000_000_500, "event_type": "receipt", "payload": {"capitalCommitId": "commit-assembly-1", "ts_ms": 1_700_000_000_500}},
            "internal_prime": {"ts_ms": 1_700_000_000_100, "event_type": "internal_prime", "payload": {"capitalCommitId": "commit-assembly-1", "updatedTsMs": 1_700_000_000_100}},
        }
        return mapping.get(domain, {})


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


class _Treasury:
    _state_repo = _TreasuryStateRepo()


class _Prime:
    _state_repo = _PrimeStateRepo()


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
            "capital_efficiency_metrics": {"deployedCapitalWei": 25 * 10**18, "updated_ts_ms": 1_700_000_000_035},
            "reinvestment_policy": {"reinvestPct": 40.0, "updated_ts_ms": 1_700_000_000_038},
        }

    def internal_prime_state(self):
        return {
            "stateReady": True,
            "borrowedUsd": 12_500.0,
            "capacityUsd": 250_000.0,
            "utilization": 0.05,
            "familyExposure": {"flash_arb": 12_500.0},
            "loanCount": 1,
            "openLoans": [{"asset": "USDC", "notional_usd": 12_500.0, "openedTsMs": 1_700_000_000_090}],
        }

    def ledger_state(self):
        return {
            "tail": [{"ts_ms": 1_700_000_000_500, "tx_type": "receipt_settlement", "receipt_id": "0xabc"}],
            "balances": {"USDC": 500.0},
        }

    def launch_state(self):
        return {"profile": {"mode": "V1_PLUS_STABLE_ALPHA"}}



def test_capital_truth_summary_assembly_kernel_wires_lower_kernels_into_canonical_truth() -> None:
    service = CapitalTruthService()
    bundle = build_capital_truth_summary_assembly(
        runtime=_Runtime(),
        now_ms=1_700_000_000_500,
        receipt_outcome_truth={},
        recovery_history={"component": "capital_truth", "degraded_count": 0},
        receipt_settlement_builder=(
            lambda *, ledger_balances, ledger_accounting: service._receipt_settlement_reconciliation(
                _Runtime(),
                ledger_balances=ledger_balances,
                ledger_accounting=ledger_accounting,
            )
        ),
        prime_ledger_reconciliation_builder=(
            lambda *, internal_prime_state, account_balances, accounting: service._internal_prime_ledger_reconciliation(
                internal_prime_state=internal_prime_state,
                account_balances=account_balances,
                accounting=accounting,
            )
        ),
        convergence_builder=(lambda **kwargs: service._capital_convergence(**kwargs)),
    )

    assert bundle.truth["canonical"] is True
    assert bundle.truth["summaryContract"]["readModel"] == "capital_truth_projection_v1"
    assert bundle.dependency_reads.capital_event_receipt["event_type"] == "receipt"
    assert bundle.derived.total_capital_wei == 32 * 10**18
    assert bundle.truth["reconciliation"]["capital_convergence"]["sources"]["bankroll_history"]["available"] is True



def test_capital_truth_service_still_emits_canonical_projection_through_summary_assembly_kernel(monkeypatch) -> None:
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: 1_700_000_000.5,
    )

    truth = CapitalTruthService().summary(_Runtime())

    assert truth["canonical"] is True
    assert truth["read_model"] == "ledgered_capital_truth_v3_converged"
    assert truth["summaryContract"]["readModel"] == "capital_truth_projection_v1"
    assert truth["categories"]["withdrawable_balance_wei"] == str(3 * 10**18)
    assert truth["reconciliation"]["capital_convergence"]["sources"]["capital_event_receipt"]["available"] is True
