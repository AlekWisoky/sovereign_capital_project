from __future__ import annotations

from victor_ai_bot.runtime_services.capital_truth_source_snapshot import (
    build_capital_truth_source_snapshots,
    build_source_snapshot,
)
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def test_capital_truth_source_snapshot_kernel_builds_canonical_source_contracts() -> None:
    bundle = build_capital_truth_source_snapshots(
        now_ms=1_700_000_000_000,
        ledger_ts_ms=1_699_999_999_000,
        realized_profit_wei=5 * 10**18,
        deployed_capital_wei=25 * 10**18,
        borrowed_usd=7500.0,
        prime_open_loan_count=2,
        capital_state={"updated_ts_ms": 1_699_999_998_000},
        capital_engine={
            "updated_ts_ms": 1_699_999_998_500,
            "family_targets": {"flash_arb": 0.7},
            "family_allocations_wei": {"flashloan_atomic": 12 * 10**18},
        },
        efficiency={"updated_ts_ms": 1_699_999_998_250},
        reinvestment={"updated_ts_ms": 1_699_999_998_750},
        receipt_settlement={
            "last_observed_ts_ms": 1_699_999_999_500,
            "pnl_receipts": {"successful_count": 1, "last_ts_ms": 1_699_999_999_500},
            "ledger_receipts": {"count": 1, "last_ts_ms": 1_699_999_999_500},
            "withdraw_history": {"count": 0, "last_ts_ms": 0},
        },
        receipt_outcome_truth={"updated_ts_ms": 1_699_999_999_250, "is_degraded": False},
        internal_prime_state={
            "updatedTsMs": 1_699_999_999_100,
            "borrowedUsd": 7500.0,
            "openLoans": [{"openedTsMs": 1_699_999_999_100}],
        },
        current_bankroll_state={
            "updated_ts_ms": 1_699_999_998_900,
            "profit_updated_ts_ms": 1_699_999_998_950,
            "sizing_updated_ts_ms": 1_699_999_998_975,
        },
        bankroll_history_event={
            "ts_ms": 1_699_999_998_975,
            "event_type": "bankroll_commit",
            "capitalCommitId": "commit-7",
            "state": {"updated_ts_ms": 1_699_999_998_975},
        },
        treasury_history_snapshot={
            "ts_ms": 1_699_999_998_800,
            "state_type": "capital_snapshot",
            "payload": {
                "updated_ts_ms": 1_699_999_998_800,
                "capitalCommitId": "commit-7",
            },
        },
        internal_prime_state_history_snapshot={
            "ts_ms": 1_699_999_999_100,
            "state_type": "prime_state",
            "payload": {"updatedTsMs": 1_699_999_999_100, "capitalCommitId": "commit-7"},
        },
        bankroll_history_enabled=True,
        treasury_history_enabled=True,
        internal_prime_history_enabled=True,
        capital_event_enabled=True,
        capital_event_bankroll={"ts_ms": 1_699_999_998_980, "event_type": "bankroll", "payload": {"capitalCommitId": "commit-7", "state": {"updated_ts_ms": 1_699_999_998_980}}},
        capital_event_treasury={"ts_ms": 1_699_999_998_810, "event_type": "treasury", "payload": {"capitalCommitId": "commit-7", "capital_engine": {"updated_ts_ms": 1_699_999_998_810}}},
        capital_event_ledger={"ts_ms": 1_699_999_999_000, "event_type": "ledger", "payload": {"tx_type": "receipt_settlement", "capitalCommitId": "commit-7"}},
        capital_event_receipt={"ts_ms": 1_699_999_999_500, "event_type": "receipt", "payload": {"ts_ms": 1_699_999_999_500, "capitalCommitId": "commit-7"}},
        capital_event_internal_prime={"ts_ms": 1_699_999_999_100, "event_type": "internal_prime", "payload": {"updatedTsMs": 1_699_999_999_100, "capitalCommitId": "commit-7"}},
        append_reason=_append_reason,
    )

    assert bundle.sources["ledger"]["freshness_class"] == "current"
    assert bundle.sources["receipt_settlement"]["details"]["ledger_receipt_count"] == 1
    assert bundle.sources["internal_prime"]["details"]["open_loan_count"] == 2
    assert bundle.sources["capital_event_receipt"]["details"]["capital_commit_id"] == "commit-7"
    assert bundle.family_targets == {"flash_arb": 0.7}
    assert bundle.family_allocations_wei == {"flashloan_atomic": 12 * 10**18}
    assert bundle.lineage_anchor_commit_id == "commit-7"


def test_capital_truth_service_still_emits_canonical_projection_through_source_snapshot_kernel(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: 1_700_000_000.0,
    )

    class _BankrollState:
        realized_profit_wei = 5 * 10**18
        last_amount_in_wei = 25 * 10**18
        success_streak = 3
        fail_streak = 0
        updated_ts_ms = 1_699_999_998_900
        profit_updated_ts_ms = 1_699_999_998_950
        sizing_updated_ts_ms = 1_699_999_998_975

    class _BankrollCfg:
        auto_reinvest_enabled = True
        reinvest_rate_pct = 40.0

    class _Bankroll:
        state = _BankrollState()
        cfg = _BankrollCfg()

    class _HistoryRepo:
        def latest_event(self):
            return {
                "ts_ms": 1_699_999_998_975,
                "event_type": "bankroll_commit",
                "state": {
                    "realized_profit_wei": 5 * 10**18,
                    "last_amount_in_wei": 25 * 10**18,
                    "success_streak": 3,
                    "fail_streak": 0,
                    "updated_ts_ms": 1_699_999_998_900,
                    "profit_updated_ts_ms": 1_699_999_998_950,
                    "sizing_updated_ts_ms": 1_699_999_998_975,
                },
                "capitalCommitId": "commit-9",
            }

    class _TreasuryStateRepo:
        def latest(self, state_type: str):
            return {
                "ts_ms": 1_699_999_998_800,
                "state_type": state_type,
                "payload": {
                    "updated_ts_ms": 1_699_999_998_800,
                    "capital_engine": {
                        "updated_ts_ms": 1_699_999_998_500,
                        "deployable_bankroll_wei": 25 * 10**18,
                        "estimated_capital_wei": 30 * 10**18,
                        "drawdown_buffer_wei": 5 * 10**18,
                        "family_allocations_wei": {"flashloan_atomic": 12 * 10**18},
                    },
                    "capitalCommitId": "commit-9",
                },
            }

    class _PrimeStateRepo:
        def latest(self, state_type: str):
            return {
                "ts_ms": 1_699_999_999_100,
                "state_type": state_type,
                "payload": {"updatedTsMs": 1_699_999_999_100, "capitalCommitId": "commit-9"},
            }

    class _CapitalEventRepo:
        def latest_event(self, domain: str):
            mapping = {
                "bankroll": {"ts_ms": 1_699_999_998_980, "event_type": "bankroll", "payload": {"capitalCommitId": "commit-9", "state": {"updated_ts_ms": 1_699_999_998_980}}},
                "treasury": {"ts_ms": 1_699_999_998_810, "event_type": "treasury", "payload": {"capitalCommitId": "commit-9", "capital_engine": {"updated_ts_ms": 1_699_999_998_810, "deployable_bankroll_wei": 25 * 10**18, "estimated_capital_wei": 30 * 10**18, "drawdown_buffer_wei": 5 * 10**18, "family_allocations_wei": {"flashloan_atomic": 12 * 10**18}}}},
                "ledger": {"ts_ms": 1_699_999_999_000, "event_type": "ledger", "payload": {"tx_type": "receipt_settlement", "capitalCommitId": "commit-9"}},
                "receipt": {"ts_ms": 1_699_999_999_500, "event_type": "receipt", "payload": {"ts_ms": 1_699_999_999_500, "capitalCommitId": "commit-9"}},
                "internal_prime": {"ts_ms": 1_699_999_999_100, "event_type": "internal_prime", "payload": {"updatedTsMs": 1_699_999_999_100, "capitalCommitId": "commit-9"}},
            }
            return mapping.get(domain, {})

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

    class _LedgerRepo:
        def all_transactions(self, chain: str):
            return [
                {
                    "ts_ms": 1_699_999_999_000,
                    "tx_type": "prime_loan_open",
                    "metadata": {"notional_usd": 7500.0},
                    "receipt_id": "loan-1",
                },
                {
                    "ts_ms": 1_699_999_999_500,
                    "tx_type": "receipt_settlement",
                    "metadata": {
                        "tx_hash": "0xabc",
                        "realized_profit_after_gas_wei": str(5 * 10**18),
                        "realized_profit_token": "WETH",
                        "realized_profit_token_wei": str(5 * 10**18),
                        "realized_profit_after_gas_usd_micro": str(12_500_000),
                    },
                    "receipt_id": "0xabc",
                },
            ]

        def transaction_balance_report(self, chain: str):
            return {
                "accountBalances": {
                    "internal_prime:borrowed_usd": {"USD": 7500.0},
                },
                "accounting": {
                    "encumberedAssets": {"USDC": 7500.0},
                    "assetAccounts": {"asset:executor": {"USDC": 7500.0}},
                },
            }

    class _Audit:
        def tail(self, limit: int = 2000):
            return []

    class _CC:
        audit = _Audit()

    class _ChainCfg:
        name = "base"

    class _ExecutionCfg:
        executor_address = "0xexecutor"
        profit_to = "bankroll"

    class _Cfg:
        chain = _ChainCfg()
        execution = _ExecutionCfg()

    class _Runtime:
        cfg = _Cfg()
        _bankroll = _Bankroll()
        _bankroll_history_repo = _HistoryRepo()
        _treasury = type("T", (), {"_state_repo": _TreasuryStateRepo()})()
        _internal_prime = type("P", (), {"_state_repo": _PrimeStateRepo()})()
        _capital_event_repo = _CapitalEventRepo()
        _capital_recovery_repo = _RecoveryRepo()
        _ledger_repo = _LedgerRepo()
        _cc = _CC()

        def treasury_state(self):
            return {"drawdown_buffer_wei": 5 * 10**18}

        def capital_engine_state(self):
            return {
                "capital_engine": {
                    "updated_ts_ms": 1_699_999_998_500,
                    "deployable_bankroll_wei": 25 * 10**18,
                    "estimated_capital_wei": 30 * 10**18,
                    "drawdown_buffer_wei": 5 * 10**18,
                    "family_targets": {"flash_arb": 0.7},
                    "family_allocations_wei": {"flashloan_atomic": 12 * 10**18},
                },
                "capital_efficiency_metrics": {"updated_ts_ms": 1_699_999_998_250},
                "reinvestment_policy": {"updated_ts_ms": 1_699_999_998_750, "reinvest_pct": 40.0},
            }

        def internal_prime_state(self):
            return {
                "stateReady": True,
                "borrowedUsd": 7500.0,
                "capacityUsd": 15000.0,
                "utilization": 0.5,
                "familyExposure": {"flash_arb": 7500.0},
                "loanCount": 1,
                "reservedCollateralUsd": 7500.0,
                "collateralizationRatio": 1.0,
                "updatedTsMs": 1_699_999_999_100,
                "openLoans": [{"asset": "USDC", "openedTsMs": 1_699_999_999_100, "collateral_reserved_usd": 7500.0}],
            }

        def launch_state(self):
            return {"profile": {"mode": "capital_balanced"}}

        def ledger_state(self):
            return {
                "tail": [{"ts_ms": 1_699_999_999_500}],
                "balances": {"USDC": 7500.0},
                "accountBalances": {"internal_prime:borrowed_usd": {"USD": 7500.0}},
                "accounting": {
                    "encumberedAssets": {"USDC": 7500.0},
                    "assetAccounts": {"asset:executor": {"USDC": 7500.0}},
                },
            }

    svc = CapitalTruthService()
    truth = svc.summary(_Runtime())

    assert truth["read_model"] == "ledgered_capital_truth_v3_converged"
    assert truth["summaryContract"]["readModel"] == "capital_truth_projection_v1"
    assert truth["reconciliation"]["capital_convergence"]["sources"]["internal_prime"]["details"]["open_loan_count"] == 1
    assert truth["reconciliation"]["receipt_settlement"]["executor_balance_snapshot"]["available"] is True
