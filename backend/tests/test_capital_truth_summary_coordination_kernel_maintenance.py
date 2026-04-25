from __future__ import annotations

from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.runtime_services.capital_truth_summary_coordination import (
    assemble_capital_truth_summary,
    build_capital_truth_summary_coordination,
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
            "capitalCommitId": "commit-coordination-1",
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
                "capitalCommitId": "commit-coordination-1",
            },
        }


class _PrimeStateRepo:
    def latest(self, state_type: str):
        return {
            "ts_ms": 1_700_000_000_100,
            "state_type": state_type,
            "payload": {"updatedTsMs": 1_700_000_000_100, "capitalCommitId": "commit-coordination-1"},
        }


class _CapitalEventRepo:
    def latest_event(self, domain: str):
        mapping = {
            "bankroll": {"ts_ms": 1_700_000_000_080, "event_type": "bankroll", "payload": {"capitalCommitId": "commit-coordination-1", "state": {"updated_ts_ms": 1_700_000_000_080}}},
            "treasury": {"ts_ms": 1_700_000_000_090, "event_type": "treasury", "payload": {"capitalCommitId": "commit-coordination-1", "capital_engine": {"updated_ts_ms": 1_700_000_000_090, "deployable_bankroll_wei": 25 * 10**18, "estimated_capital_wei": 30 * 10**18, "drawdown_buffer_wei": 5 * 10**18, "family_allocations_wei": {"flashloan_atomic": 12 * 10**18}}}},
            "ledger": {"ts_ms": 1_700_000_000_200, "event_type": "ledger", "payload": {"capitalCommitId": "commit-coordination-1", "tx_type": "receipt_settlement"}},
            "receipt": {"ts_ms": 1_700_000_000_500, "event_type": "receipt", "payload": {"capitalCommitId": "commit-coordination-1", "ts_ms": 1_700_000_000_500}},
            "internal_prime": {"ts_ms": 1_700_000_000_100, "event_type": "internal_prime", "payload": {"capitalCommitId": "commit-coordination-1", "updatedTsMs": 1_700_000_000_100}},
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


def test_capital_truth_summary_coordination_kernel_matches_service_summary_without_recovery_repo(monkeypatch) -> None:
    monkeypatch.setattr("victor_ai_bot.runtime_services.capital_truth_service_shell.time.time", lambda: 1_700_000_000.500)
    runtime = _Runtime()
    service = CapitalTruthService()
    coordination = build_capital_truth_summary_coordination(
        service=service,
        runtime=runtime,
        now_ms=1_700_000_000_500,
    )

    bundle = assemble_capital_truth_summary(
        runtime=runtime,
        coordination=coordination,
    )

    assert coordination.recovery_history == {}
    assert coordination.receipt_outcome_truth == {}
    assert bundle.truth["canonical"] is True
    assert bundle.truth["summaryContract"]["readModel"] == "capital_truth_projection_v1"
    assert service.summary(runtime) == bundle.truth
