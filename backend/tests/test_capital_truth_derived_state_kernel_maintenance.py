from __future__ import annotations

from victor_ai_bot.runtime_services.capital_truth_derived_state import (
    build_capital_truth_derived_state,
)
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService


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


def test_capital_truth_derived_state_kernel_computes_totals_exposure_and_family_rollups() -> None:
    bundle = build_capital_truth_derived_state(
        capital_engine={
            "deployable_bankroll_wei": 25 * 10**18,
            "drawdown_buffer_wei": 5 * 10**18,
            "estimated_capital_wei": 30 * 10**18,
            "family_targets": {"flash_arb": 0.6, "funding_arb": 0.4},
        },
        efficiency={"deployedCapitalWei": 25 * 10**18},
        reinvestment={"reinvestPct": 40.0},
        treasury_state={"drawdown_buffer_wei": 5 * 10**18},
        internal_prime_state={
            "stateReady": True,
            "borrowedUsd": 7500.0,
            "capacityUsd": 15000.0,
            "utilization": 0.5,
            "familyExposure": {"flash_arb": 5000.0},
            "loanCount": 1,
            "openLoans": [{"collateral_reserved_usd": 8200.0}],
            "collateralizationRatio": 1.2,
        },
        bankroll=_Bankroll(),
        bankroll_state=_BankrollState(),
    )

    assert bundle.total_capital_wei == 32 * 10**18
    assert bundle.retained_profit_wei == 2 * 10**18
    assert bundle.withdrawable_balance_wei == 3 * 10**18
    assert bundle.locked_capital_wei == 8200 * 10**18
    assert bundle.prime_family_exposure == {"flash_arb": 5000.0}
    assert bundle.categories["reserved_capital_wei"] == str(5 * 10**18)
    assert bundle.family_allocations == {"flash_arb": 0.6, "funding_arb": 0.4}
    assert bundle.family_capital_plan[0]["id"] == "flash_arb"


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
            "capitalCommitId": "commit-11",
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
                "capitalCommitId": "commit-11",
            },
        }


class _PrimeStateRepo:
    def latest(self, state_type: str):
        return {
            "ts_ms": 1_699_999_999_100,
            "state_type": state_type,
            "payload": {"updatedTsMs": 1_699_999_999_100, "capitalCommitId": "commit-11"},
        }


class _CapitalEventRepo:
    def latest_event(self, domain: str):
        mapping = {
            "bankroll": {"ts_ms": 1_699_999_998_980, "event_type": "bankroll", "payload": {"capitalCommitId": "commit-11", "state": {"updated_ts_ms": 1_699_999_998_980}}},
            "treasury": {"ts_ms": 1_699_999_998_810, "event_type": "treasury", "payload": {"capitalCommitId": "commit-11", "capital_engine": {"updated_ts_ms": 1_699_999_998_810, "deployable_bankroll_wei": 25 * 10**18, "estimated_capital_wei": 30 * 10**18, "drawdown_buffer_wei": 5 * 10**18, "family_allocations_wei": {"flashloan_atomic": 12 * 10**18}}}},
            "ledger": {"ts_ms": 1_699_999_999_000, "event_type": "ledger", "payload": {"tx_type": "receipt_settlement", "capitalCommitId": "commit-11"}},
            "receipt": {"ts_ms": 1_699_999_999_500, "event_type": "receipt", "payload": {"ts_ms": 1_699_999_999_500, "capitalCommitId": "commit-11"}},
            "internal_prime": {"ts_ms": 1_699_999_999_100, "event_type": "internal_prime", "payload": {"updatedTsMs": 1_699_999_999_100, "capitalCommitId": "commit-11"}},
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
    _db = object()
    _capital_recovery_repo = _RecoveryRepo()
    _ledger_repo = _LedgerRepo()
    _cc = _CC()
    _history_repo = _HistoryRepo()
    _treasury_state_repo = _TreasuryStateRepo()
    _internal_prime_state_repo = _PrimeStateRepo()
    _capital_event_repo = _CapitalEventRepo()

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": 25 * 10**18,
                "drawdown_buffer_wei": 5 * 10**18,
                "estimated_capital_wei": 30 * 10**18,
                "family_targets": {"flash_arb": 0.6},
                "family_allocations_wei": {"flashloan_atomic": 12 * 10**18},
                "updated_ts_ms": 1_699_999_998_500,
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": 25 * 10**18, "updated_ts_ms": 1_699_999_998_250},
            "reinvestment_policy": {"reinvestPct": 40.0, "updated_ts_ms": 1_699_999_998_750},
            "updated_ts_ms": 1_699_999_998_000,
        }

    def treasury_state(self):
        return {"enabled": True, "drawdown_buffer_wei": 5 * 10**18}

    def internal_prime_state(self):
        return {
            "stateReady": True,
            "borrowedUsd": 7500.0,
            "capacityUsd": 15_000.0,
            "utilization": 0.5,
            "familyExposure": {"flash_arb": 5000.0},
            "loanCount": 1,
            "openLoans": [{"asset": "USDC", "collateral_reserved_usd": 7500.0}],
            "updatedTsMs": 1_699_999_999_100,
        }

    def ledger_state(self):
        return {
            "balances": {"USDC": 500.0},
            "tail": [{"ts_ms": 1_699_999_999_500, "asset": "USDC", "amount": 500.0}],
            "transactions": [],
        }

    def launch_state(self):
        return {"profile": {"mode": "V1_PLUS_STABLE_ALPHA"}}


def test_capital_truth_service_still_emits_canonical_projection_through_derived_state_kernel(monkeypatch) -> None:
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: 1_700_000_000.0,
    )

    truth = CapitalTruthService().summary(_Runtime())

    assert truth["canonical"] is True
    assert truth["categories"]["total_capital_wei"] == str(32 * 10**18)
    assert truth["categories"]["withdrawable_balance_wei"] == str(3 * 10**18)
    assert truth["family_allocations"] == {"flash_arb": 0.6}
    assert truth["familyCapitalPlan"][0]["id"] == "flash_arb"
