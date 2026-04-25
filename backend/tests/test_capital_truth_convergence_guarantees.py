from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.command_center_overlay import AuditStore
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.bankroll_repository import BankrollEventRepository
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.persistence.repositories.treasury_state_repository import TreasuryStateRepository
from victor_ai_bot.pnl import PnLStore
from victor_ai_bot.runtime_services.capital_truth_health_contract import (
    runtime_capital_truth_health,
)
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.treasury.ledger import TreasuryLedger


class _Chain:
    name = "ethereum"


class _Execution:
    executor_address = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    profit_to = "0x1111111111111111111111111111111111111111"
    withdraw_mode = "txdata"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _BankrollCfg:
    auto_reinvest_enabled = False
    reinvest_rate_pct = 0.0


class _BankrollState:
    def __init__(
        self,
        *,
        realized_profit_wei: int = 0,
        last_amount_in_wei: int = 0,
        updated_ts_ms: int = 0,
        profit_updated_ts_ms: int = 0,
        sizing_updated_ts_ms: int = 0,
    ):
        self.realized_profit_wei = int(realized_profit_wei)
        self.last_amount_in_wei = int(last_amount_in_wei)
        self.success_streak = 0
        self.fail_streak = 0
        self.updated_ts_ms = int(updated_ts_ms or 0)
        self.profit_updated_ts_ms = int(profit_updated_ts_ms or 0)
        self.sizing_updated_ts_ms = int(sizing_updated_ts_ms or 0)


class _Bankroll:
    cfg = _BankrollCfg()

    def __init__(
        self,
        *,
        realized_profit_wei: int = 0,
        last_amount_in_wei: int = 0,
        updated_ts_ms: int = 0,
        profit_updated_ts_ms: int = 0,
        sizing_updated_ts_ms: int = 0,
    ):
        self.state = _BankrollState(
            realized_profit_wei=realized_profit_wei,
            last_amount_in_wei=last_amount_in_wei,
            updated_ts_ms=updated_ts_ms,
            profit_updated_ts_ms=profit_updated_ts_ms,
            sizing_updated_ts_ms=sizing_updated_ts_ms,
        )


class _ConvergenceRuntime:
    cfg = _Cfg()

    def __init__(
        self,
        tmp_path,
        *,
        realized_profit_wei: int = 0,
        last_amount_in_wei: int = 0,
        bankroll_updated_ts_ms: int = 0,
        bankroll_profit_updated_ts_ms: int = 0,
        bankroll_sizing_updated_ts_ms: int = 0,
    ):
        self._db = PersistenceDB(str(tmp_path / "state.sqlite3"))
        self._ledger_repo = LedgerRepository(self._db)
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain=self.cfg.chain.name)
        self._pnl = PnLStore(str(tmp_path / "pnl.sqlite3"))
        self._cc = SimpleNamespace(audit=AuditStore(str(tmp_path / "cc_audit_ethereum.jsonl")))
        self._bankroll = _Bankroll(
            realized_profit_wei=realized_profit_wei,
            last_amount_in_wei=last_amount_in_wei,
            updated_ts_ms=bankroll_updated_ts_ms,
            profit_updated_ts_ms=bankroll_profit_updated_ts_ms,
            sizing_updated_ts_ms=bankroll_sizing_updated_ts_ms,
        )
        self._capital_state = {
            "capital_engine": {},
            "capital_efficiency_metrics": {},
            "reinvestment_policy": {},
        }
        self._internal_prime_state = {
            "borrowedUsd": 0.0,
            "capacityUsd": 1_000_000.0,
            "utilization": 0.0,
            "familyExposure": {},
            "openLoans": [],
            "disputedLoans": [],
            "loanCount": 0,
            "reservedCollateralUsd": 0.0,
            "collateralizationRatio": 0.0,
            "stateReady": True,
            "stateStatus": "ok",
            "stateReasonCode": "",
        }
        self._ledger_state = {
            "balances": {},
            "accountBalances": {},
            "accounting": {},
            "tail": [],
            "transactions": [],
        }

    def treasury_state(self):
        return {"enabled": True}

    def capital_engine_state(self):
        return dict(self._capital_state)

    def internal_prime_state(self):
        return dict(self._internal_prime_state)

    def launch_state(self):
        return {}

    def ledger_state(self):
        return dict(self._ledger_state)


async def _seed_trade(
    runtime: _ConvergenceRuntime, *, tx_hash: str, realized_after: str, ts_s: int
):
    await runtime._pnl.init()
    trade_id = await runtime._pnl.add_trade(
        {
            "ts": int(ts_s),
            "chain": runtime.cfg.chain.name,
            "opportunity_id": "opp-1",
            "route_id": "route-1",
            "tx_hash": tx_hash,
            "mode": "auto",
            "dry_run": False,
            "ok": True,
            "reason": "submitted",
            "expected_gross_profit_wei": "110",
            "expected_profit_after_costs_wei": realized_after,
            "estimated_gas_cost_wei": "10",
            "flashloan_fee_wei": "1",
            "gas_limit": 21000,
            "max_fee_wei": "1",
            "priority_fee_wei": "1",
            "strategy_type": "flash_arb",
            "income_stream": "arb",
            "venue_path": "uniswap",
        }
    )

    import sqlite3

    con = sqlite3.connect(runtime._pnl.path)
    try:
        con.execute(
            "UPDATE trades SET receipt_status=?, realized_profit_after_gas_wei=?, realized_profit_token=?, realized_profit_token_wei=?, realized_profit_after_gas_usd_micro=? WHERE id=?",
            (
                1,
                str(realized_after),
                "USDC",
                str(realized_after),
                str(realized_after),
                int(trade_id),
            ),
        )
        con.commit()
    finally:
        con.close()


def test_capital_truth_service_degrades_on_bankroll_receipt_realized_profit_mismatch(
    tmp_path, monkeypatch
):
    fixed_now_ms = 1_700_000_000_000
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _ConvergenceRuntime(
        tmp_path,
        realized_profit_wei=250,
        last_amount_in_wei=1_000,
    )
    runtime._capital_state = {
        "updated_ts_ms": fixed_now_ms - 60_000,
        "capital_engine": {
            "deployable_bankroll_wei": 1_000,
            "estimated_capital_wei": 1_000,
            "drawdown_buffer_wei": 0,
        },
        "capital_efficiency_metrics": {"deployedCapitalWei": 1_000},
        "reinvestment_policy": {},
    }
    runtime._ledger_state = {
        "balances": {"USD": 100.0},
        "accountBalances": {},
        "accounting": {},
        "tail": [{"ts_ms": fixed_now_ms - 60_000, "asset": "USD", "delta": 100.0}],
        "transactions": [],
    }
    asyncio.run(
        _seed_trade(
            runtime,
            tx_hash="0xabc",
            realized_after="100",
            ts_s=(fixed_now_ms // 1000) - 60,
        )
    )
    ReceiptService().synchronize_settlement_accounting(
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

    truth = CapitalTruthService().summary(runtime)

    assert truth["status"] == "degraded"
    assert "bankroll_receipt_realized_profit_mismatch" in set(truth["status_reasons"])
    assert (
        truth["reconciliation"]["capital_convergence"]["derived"][
            "receipt_realized_profit_after_gas_wei_total"
        ]
        == "100"
    )


def test_capital_truth_service_degrades_on_stale_material_sources(tmp_path, monkeypatch):
    fixed_now_ms = 1_700_000_000_000
    stale_ts_ms = fixed_now_ms - (2 * 24 * 60 * 60 * 1000)
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _ConvergenceRuntime(tmp_path)
    runtime._capital_state = {
        "ts": stale_ts_ms // 1000,
        "capital_engine": {
            "deployable_bankroll_wei": 500 * 10**18,
            "estimated_capital_wei": 500 * 10**18,
            "drawdown_buffer_wei": 0,
            "family_targets": {"flash_arb": 0.4},
            "family_allocations_wei": {"flash_arb": 200 * 10**18},
        },
        "capital_efficiency_metrics": {"deployedCapitalWei": 500 * 10**18},
        "reinvestment_policy": {},
    }
    runtime._internal_prime_state = {
        "borrowedUsd": 100.0,
        "capacityUsd": 1_000.0,
        "utilization": 0.1,
        "familyExposure": {"flash_arb": 100.0},
        "openLoans": [
            {"asset": "ETH", "collateral_reserved_usd": 100.0, "openedTsMs": stale_ts_ms}
        ],
        "disputedLoans": [],
        "loanCount": 1,
        "reservedCollateralUsd": 100.0,
        "collateralizationRatio": 1.0,
        "stateReady": True,
        "stateStatus": "ok",
        "stateReasonCode": "",
    }
    runtime._ledger_state = {
        "balances": {"USD": 500.0},
        "accountBalances": {"internal_prime:borrowed_usd": {"USD": 100.0}},
        "accounting": {"encumberedAssets": {"ETH": 100.0}},
        "tail": [{"ts_ms": fixed_now_ms - 60_000, "asset": "USD", "delta": 500.0}],
        "transactions": [],
    }

    truth = CapitalTruthService().summary(runtime)
    reasons = set(truth["status_reasons"])

    assert truth["status"] == "degraded"
    assert "capital_engine_freshness_stale" in reasons
    assert "family_allocations_freshness_stale" in reasons
    assert "internal_prime_freshness_stale" in reasons
    assert "bankroll_freshness_unknown" in reasons


def test_capital_truth_service_degrades_on_family_allocation_overcommitment(tmp_path, monkeypatch):
    fixed_now_ms = 1_700_000_000_000
    recent_ts_ms = fixed_now_ms - 60_000
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _ConvergenceRuntime(tmp_path)
    runtime._capital_state = {
        "updated_ts_ms": recent_ts_ms,
        "capital_engine": {
            "deployable_bankroll_wei": 100,
            "estimated_capital_wei": 100,
            "drawdown_buffer_wei": 0,
            "family_targets": {"flash_arb": 0.8, "carry": 0.5},
            "family_allocations_wei": {"flash_arb": 80, "carry": 40, "unknown": 5},
        },
        "capital_efficiency_metrics": {"deployedCapitalWei": 100},
        "reinvestment_policy": {},
    }
    runtime._ledger_state = {
        "balances": {"USD": 100.0},
        "accountBalances": {},
        "accounting": {},
        "tail": [{"ts_ms": recent_ts_ms, "asset": "USD", "delta": 100.0}],
        "transactions": [],
    }

    truth = CapitalTruthService().summary(runtime)
    reasons = set(truth["status_reasons"])

    assert truth["status"] == "degraded"
    assert "family_targets_overallocated" in reasons
    assert "family_allocations_exceed_deployable_capital" in reasons
    assert "family_allocation_target_mismatch" in reasons


def test_runtime_capital_truth_health_uses_canonical_truth_when_only_contract_is_passed():
    class _Runtime:
        def capital_truth_state(self):
            return {
                "ok": True,
                "status": "degraded",
                "reason_code": "capital_engine_freshness_stale",
                "reason_codes": ["capital_engine_freshness_stale"],
                "status_reasons": ["capital_engine_freshness_stale"],
                "ts_ms": 1_700_000_000_000,
                "ledger": {"last_ts_ms": 1_699_999_940_000},
            }

    health = runtime_capital_truth_health(
        _Runtime(),
        capital_truth={"contractVersion": "canonical_capital_summary_v1"},
        fund_summary={},
    )

    assert health["reasonCode"] == "capital_engine_freshness_stale"
    assert health["blocked"] is True


def test_capital_truth_service_uses_native_bankroll_timestamps(tmp_path, monkeypatch):
    fixed_now_ms = 1_700_000_000_000
    recent_ts_ms = fixed_now_ms - 60_000
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _ConvergenceRuntime(
        tmp_path,
        last_amount_in_wei=100,
        bankroll_updated_ts_ms=recent_ts_ms,
        bankroll_sizing_updated_ts_ms=recent_ts_ms,
    )
    runtime._capital_state = {
        "updated_ts_ms": recent_ts_ms,
        "capital_engine": {
            "deployable_bankroll_wei": 100,
            "estimated_capital_wei": 100,
            "drawdown_buffer_wei": 0,
        },
        "capital_efficiency_metrics": {"deployedCapitalWei": 100, "updated_ts_ms": recent_ts_ms},
        "reinvestment_policy": {"updated_ts_ms": recent_ts_ms},
    }
    runtime._ledger_state = {
        "balances": {"USD": 100.0},
        "accountBalances": {},
        "accounting": {},
        "tail": [{"ts_ms": recent_ts_ms, "asset": "USD", "delta": 100.0}],
        "transactions": [],
    }

    truth = CapitalTruthService().summary(runtime)

    assert truth["status"] == "ok"
    bankroll_source = truth["reconciliation"]["capital_convergence"]["sources"]["bankroll"]
    assert bankroll_source["ts_ms"] == recent_ts_ms
    assert bankroll_source["details"]["native_ts_ms"] == recent_ts_ms
    assert "bankroll_freshness_stale" not in set(truth["status_reasons"])


def test_capital_truth_service_uses_nested_capital_engine_timestamp_fields(tmp_path, monkeypatch):
    fixed_now_ms = 1_700_000_000_000
    recent_ts_ms = fixed_now_ms - 60_000
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _ConvergenceRuntime(
        tmp_path,
        bankroll_updated_ts_ms=recent_ts_ms,
    )
    runtime._capital_state = {
        "capital_engine": {
            "deployable_bankroll_wei": 100,
            "estimated_capital_wei": 100,
            "drawdown_buffer_wei": 0,
            "updated_ts_ms": recent_ts_ms,
        },
        "capital_efficiency_metrics": {},
        "reinvestment_policy": {},
    }
    runtime._ledger_state = {
        "balances": {"USD": 100.0},
        "accountBalances": {},
        "accounting": {},
        "tail": [{"ts_ms": recent_ts_ms, "asset": "USD", "delta": 100.0}],
        "transactions": [],
    }

    truth = CapitalTruthService().summary(runtime)

    assert truth["status"] == "ok"
    capital_source = truth["reconciliation"]["capital_convergence"]["sources"]["capital_engine"]
    assert capital_source["ts_ms"] == recent_ts_ms
    assert "capital_engine_freshness_stale" not in set(truth["status_reasons"])


def test_capital_truth_service_degrades_on_bankroll_state_history_mismatch(tmp_path, monkeypatch):
    fixed_now_ms = 1_700_000_000_000
    recent_ts_ms = fixed_now_ms - 60_000
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _ConvergenceRuntime(
        tmp_path,
        realized_profit_wei=250,
        last_amount_in_wei=100,
        bankroll_updated_ts_ms=recent_ts_ms,
        bankroll_profit_updated_ts_ms=recent_ts_ms,
        bankroll_sizing_updated_ts_ms=recent_ts_ms,
    )
    runtime._capital_state = {
        "updated_ts_ms": recent_ts_ms,
        "capital_engine": {
            "deployable_bankroll_wei": 100,
            "estimated_capital_wei": 100,
            "drawdown_buffer_wei": 0,
            "updated_ts_ms": recent_ts_ms,
        },
        "capital_efficiency_metrics": {"deployedCapitalWei": 100, "updated_ts_ms": recent_ts_ms},
        "reinvestment_policy": {"updated_ts_ms": recent_ts_ms},
    }
    runtime._ledger_state = {
        "balances": {"USD": 100.0},
        "accountBalances": {},
        "accounting": {},
        "tail": [{"ts_ms": recent_ts_ms, "asset": "USD", "delta": 100.0}],
        "transactions": [],
    }
    runtime._bankroll_history_repo = BankrollEventRepository(
        runtime._db, chain=runtime.cfg.chain.name
    )
    runtime._bankroll_history_repo.append_event(
        ts_ms=recent_ts_ms,
        event_type="trade_recorded",
        state={
            "realized_profit_wei": 125,
            "last_amount_in_wei": 100,
            "success_streak": 0,
            "fail_streak": 0,
            "updated_ts_ms": recent_ts_ms,
            "profit_updated_ts_ms": recent_ts_ms,
            "sizing_updated_ts_ms": recent_ts_ms,
        },
        payload={},
    )

    truth = CapitalTruthService().summary(runtime)

    reasons = set(truth["status_reasons"])
    assert truth["status"] == "degraded"
    assert "bankroll_state_history_mismatch" in reasons
    bankroll_history = truth["reconciliation"]["capital_convergence"]["sources"]["bankroll_history"]
    assert "realized_profit_wei" in set(bankroll_history["details"]["mismatch_fields"])


def test_capital_truth_service_degrades_on_treasury_state_history_runtime_mismatch(
    tmp_path, monkeypatch
):
    fixed_now_ms = 1_700_000_000_000
    recent_ts_ms = fixed_now_ms - 60_000
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _ConvergenceRuntime(
        tmp_path,
        last_amount_in_wei=100,
        bankroll_updated_ts_ms=recent_ts_ms,
    )
    runtime._capital_state = {
        "updated_ts_ms": recent_ts_ms,
        "capital_engine": {
            "deployable_bankroll_wei": 100,
            "estimated_capital_wei": 100,
            "drawdown_buffer_wei": 0,
            "family_allocations_wei": {"flash_arb": 100},
            "updated_ts_ms": recent_ts_ms,
        },
        "capital_efficiency_metrics": {"deployedCapitalWei": 100, "updated_ts_ms": recent_ts_ms},
        "reinvestment_policy": {"updated_ts_ms": recent_ts_ms},
    }
    runtime._ledger_state = {
        "balances": {"USD": 100.0},
        "accountBalances": {},
        "accounting": {},
        "tail": [{"ts_ms": recent_ts_ms, "asset": "USD", "delta": 100.0}],
        "transactions": [],
    }
    treasury_repo = TreasuryStateRepository(runtime._db, chain=runtime.cfg.chain.name)
    runtime._treasury = SimpleNamespace(_state_repo=treasury_repo)
    treasury_repo.append_snapshot(
        ts_ms=recent_ts_ms,
        state_type="capital_snapshot",
        payload={
            "updated_ts_ms": recent_ts_ms,
            "capital_engine": {
                "updated_ts_ms": recent_ts_ms,
                "deployable_bankroll_wei": 50,
                "estimated_capital_wei": 50,
                "drawdown_buffer_wei": 0,
                "family_allocations_wei": {"flash_arb": 50},
            },
            "capital_efficiency_metrics": {"updated_ts_ms": recent_ts_ms},
            "reinvestment_policy": {"updated_ts_ms": recent_ts_ms},
        },
    )

    truth = CapitalTruthService().summary(runtime)

    reasons = set(truth["status_reasons"])
    assert truth["status"] == "degraded"
    assert "capital_engine_history_runtime_mismatch" in reasons
    treasury_history = truth["reconciliation"]["capital_convergence"]["sources"][
        "treasury_state_history"
    ]
    mismatch_fields = set(treasury_history["details"]["mismatch_fields"])
    assert "deployable_bankroll_wei" in mismatch_fields
    assert "family_allocations_wei" in mismatch_fields


def test_capital_truth_service_treats_alias_family_allocation_as_synchronized_target(tmp_path, monkeypatch):
    fixed_now_ms = 1_700_000_000_000
    recent_ts_ms = fixed_now_ms - 60_000
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _ConvergenceRuntime(tmp_path)
    runtime._capital_state = {
        "updated_ts_ms": recent_ts_ms,
        "capital_engine": {
            "deployable_bankroll_wei": 100 * 10**18,
            "estimated_capital_wei": 100 * 10**18,
            "drawdown_buffer_wei": 0,
            "family_targets": {"flashloan_atomic": 0.6},
            "family_allocations_wei": {"flash_arb": 60 * 10**18},
        },
        "capital_efficiency_metrics": {"deployedCapitalWei": 100 * 10**18},
        "reinvestment_policy": {},
    }
    runtime._ledger_state = {
        "balances": {"USD": 100.0},
        "accountBalances": {},
        "accounting": {},
        "tail": [{"ts_ms": recent_ts_ms, "asset": "USD", "delta": 100.0}],
        "transactions": [],
    }

    truth = CapitalTruthService().summary(runtime)
    reasons = set(truth["status_reasons"])

    assert "family_allocation_target_mismatch" not in reasons
    assert truth["familyCapitalPlan"][0]["resolvedTargetKey"] == "flashloan_atomic"
    assert truth["familyCapitalPlan"][0]["resolvedAllocationKey"] == "flash_arb"
