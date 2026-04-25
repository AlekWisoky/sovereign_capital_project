from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.command_center_overlay import AuditStore
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.bankroll_repository import BankrollEventRepository
from victor_ai_bot.persistence.repositories.capital_event_repository import CapitalEventRepository
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.pnl import PnLStore
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
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


class _BankrollCfg:
    auto_reinvest_enabled = False
    reinvest_rate_pct = 0.0


class _BusBankrollState:
    def __init__(self, *, realized_profit_wei: int, last_amount_in_wei: int, updated_ts_ms: int):
        self.realized_profit_wei = int(realized_profit_wei)
        self.last_amount_in_wei = int(last_amount_in_wei)
        self.success_streak = 0
        self.fail_streak = 0
        self.updated_ts_ms = int(updated_ts_ms)
        self.profit_updated_ts_ms = int(updated_ts_ms)
        self.sizing_updated_ts_ms = int(updated_ts_ms)


class _BusBankroll:
    cfg = _BankrollCfg()

    def __init__(self, *, realized_profit_wei: int, last_amount_in_wei: int, updated_ts_ms: int):
        self.state = _BusBankrollState(
            realized_profit_wei=realized_profit_wei,
            last_amount_in_wei=last_amount_in_wei,
            updated_ts_ms=updated_ts_ms,
        )


class _CapitalBusRuntime:
    cfg = _Cfg()

    def __init__(self, tmp_path, *, realized_profit_wei: int = 100, last_amount_in_wei: int = 100):
        self._db = PersistenceDB(str(tmp_path / "state.sqlite3"))
        self._capital_event_repo = CapitalEventRepository(self._db, chain=self.cfg.chain.name)
        self._ledger_repo = LedgerRepository(
            self._db,
            capital_event_repo=self._capital_event_repo,
            chain=self.cfg.chain.name,
        )
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain=self.cfg.chain.name)
        self._pnl = PnLStore(str(tmp_path / "pnl.sqlite3"))
        self._cc = SimpleNamespace(audit=AuditStore(str(tmp_path / "cc_audit_ethereum.jsonl")))
        self._bankroll = _BusBankroll(
            realized_profit_wei=realized_profit_wei,
            last_amount_in_wei=last_amount_in_wei,
            updated_ts_ms=1_700_000_000_000,
        )
        self._capital_state = {
            "updated_ts_ms": 1_700_000_000_000,
            "capital_engine": {
                "deployable_bankroll_wei": last_amount_in_wei,
                "estimated_capital_wei": last_amount_in_wei,
                "drawdown_buffer_wei": 0,
                "updated_ts_ms": 1_700_000_000_000,
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": last_amount_in_wei},
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
            "balances": {"USD": 100.0},
            "accountBalances": {},
            "accounting": {},
            "tail": [{"ts_ms": 1_700_000_000_000, "asset": "USD", "delta": 100.0}],
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


def _seed_trade(runtime: _CapitalBusRuntime, *, tx_hash: str, realized_after: str = "100") -> None:
    async def _seed() -> None:
        await runtime._pnl.init()
        trade_id = await runtime._pnl.add_trade(
            {
                "ts": 1,
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

    asyncio.run(_seed())


def test_bankroll_manager_publishes_capital_event_bus_events(tmp_path, monkeypatch):
    state_path = tmp_path / "bankroll_state.json"
    db = PersistenceDB(str(tmp_path / "bankroll.sqlite3"))
    history_repo = BankrollEventRepository(db, chain="ethereum")
    capital_event_repo = CapitalEventRepository(db, chain="ethereum")
    times = iter([1_700_000_000.0, 1_700_000_060.0, 1_700_000_120.0])
    monkeypatch.setattr("victor_ai_bot.bankroll.time.time", lambda: next(times))
    manager = BankrollManager(
        BankrollConfig(base_borrow_amount_wei=100, max_borrow_amount_wei=500),
        state_path=str(state_path),
        history_repo=history_repo,
        capital_event_repo=capital_event_repo,
    )
    manager.record_trade(success=True, realized_profit_after_gas_wei=25, amount_in_wei=100)
    manager.next_amount_in()

    event = capital_event_repo.latest_event(domain="bankroll")
    assert event["event_type"] == "sizing_decision"
    assert event["payload"]["state"]["realized_profit_wei"] == 25


def test_treasury_runtime_publishes_capital_snapshot_domain_events(tmp_path, monkeypatch):
    monkeypatch.setattr("victor_ai_bot.treasury.runtime.time.time", lambda: 1_700_000_000.0)
    db = PersistenceDB(str(tmp_path / "treasury.sqlite3"))
    capital_event_repo = CapitalEventRepository(db, chain="ethereum")
    runtime = TreasuryRuntime(
        cfg=TreasuryConfig(enabled=True),
        data_dir=str(tmp_path),
        db=db,
        chain="ethereum",
        capital_event_repo=capital_event_repo,
    )
    snapshot = runtime.pre_select_strategy(
        bankroll_state={
            "realized_profit_wei": 0,
            "last_amount_in_wei": 100,
            "updated_ts_ms": 1_699_999_940_000,
            "profit_updated_ts_ms": 1_699_999_940_000,
            "sizing_updated_ts_ms": 1_699_999_940_000,
        },
        volatility_regime="balanced",
    )

    event = capital_event_repo.latest_event(domain="treasury")
    assert event["event_type"] == "capital_snapshot"
    assert (
        event["payload"]["capital_engine"]["updated_ts_ms"]
        == snapshot["capital_engine"]["updated_ts_ms"]
    )


def test_receipt_and_ledger_publish_capital_event_bus_events(tmp_path):
    runtime = _CapitalBusRuntime(tmp_path)
    _seed_trade(runtime, tx_hash="0xabc", realized_after="100")
    out = ReceiptService().synchronize_settlement_accounting(
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
    assert out["ok"] is True

    ledger_event = runtime._capital_event_repo.latest_event(domain="ledger")
    receipt_event = runtime._capital_event_repo.latest_event(domain="receipt")
    assert ledger_event["event_type"] == "receipt_settlement"
    assert ledger_event["receipt_id"] == "0xabc"
    assert receipt_event["event_type"] == "settlement_recorded"
    assert receipt_event["receipt_id"] == "0xabc"


def test_capital_truth_service_degrades_on_capital_event_bus_mismatch(tmp_path, monkeypatch):
    fixed_now_ms = 1_700_000_000_000
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: fixed_now_ms / 1000.0,
    )
    runtime = _CapitalBusRuntime(tmp_path, realized_profit_wei=250, last_amount_in_wei=100)
    runtime._capital_event_repo.append_event(
        ts_ms=fixed_now_ms - 60_000,
        domain="bankroll",
        event_type="trade_recorded",
        source="test",
        entity_id="bankroll_state",
        payload={
            "state": {
                "realized_profit_wei": 125,
                "last_amount_in_wei": 100,
                "success_streak": 0,
                "fail_streak": 0,
                "updated_ts_ms": fixed_now_ms - 60_000,
                "profit_updated_ts_ms": fixed_now_ms - 60_000,
                "sizing_updated_ts_ms": fixed_now_ms - 60_000,
            }
        },
    )
    runtime._capital_event_repo.append_event(
        ts_ms=fixed_now_ms - 60_000,
        domain="treasury",
        event_type="capital_snapshot",
        source="test",
        entity_id="treasury_runtime",
        payload={
            "updated_ts_ms": fixed_now_ms - 60_000,
            "capital_engine": {
                "updated_ts_ms": fixed_now_ms - 60_000,
                "deployable_bankroll_wei": 90,
                "estimated_capital_wei": 90,
                "drawdown_buffer_wei": 0,
            },
        },
    )

    truth = CapitalTruthService().summary(runtime)
    reasons = set(truth["status_reasons"])
    assert truth["status"] == "degraded"
    assert "bankroll_capital_event_mismatch" in reasons
    assert "capital_engine_capital_event_mismatch" in reasons
