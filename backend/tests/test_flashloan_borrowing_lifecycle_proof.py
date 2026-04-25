from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.treasury.config import ProfitGoal, TreasuryConfig
from victor_ai_bot.treasury.ledger import TreasuryLedger
from victor_ai_bot.treasury.runtime import TreasuryRuntime


class _FlashloanLiveRuntime:
    def __init__(self) -> None:
        self._pending = {
            "0xflash": {
                "flashloan_fee_wei": "4500",
                "borrow_cost_usd": 1.25,
                "capture_meta": {
                    "lane": "PRIVATE",
                    "endpoint_hint": "rpc-fast",
                    "relay_hint": "relay-a",
                    "metadata": {
                        "endpoint_selection": {
                            "endpoint": "rpc-fast",
                            "reason": "quality_ranked",
                            "universe": {"reason": "operator_preferences"},
                        },
                        "route_plan": {
                            "selected_venues": ["uni", "curve"],
                            "fallback_tree": [{"selected_venues": ["uni"]}],
                        },
                        "execution_route_plan": {
                            "selected_venues": ["uni", "curve"],
                            "fallback_tree": [{"selected_venues": ["uni"]}],
                            "executable": True,
                            "route_invalid_causes": [],
                        },
                        "flashloan_resilience": {
                            "selected_provider": "aave",
                            "fallback_provider": "balancer",
                            "provider_priority": ["aave", "balancer"],
                            "reserve_distortion": 0.12,
                            "route_viable": True,
                            "sizing": {
                                "borrow_mult": 1.4,
                                "size_mult": 1.1,
                                "provider_choice_reason": "deepest_liquidity",
                                "borrowCostUsd": 1.25,
                            },
                        },
                    },
                },
                "route_family": "flashloan_atomic",
                "strategy_family": "flashloan_atomic",
                "created_at_ms": 123,
            }
        }


class _FlashloanSettlementRuntime:
    def __init__(self, tmp_path: Path):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="eth"), execution=SimpleNamespace(auto_trading=True)
        )
        self._auto_trading = True
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
        self._ledger_repo = LedgerRepository(PersistenceDB(str(tmp_path / "state.sqlite3")))
        self._treasury = TreasuryRuntime(
            cfg=TreasuryConfig(enabled=True, goal=ProfitGoal(target_return_percentage=5.0)),
            data_dir=str(tmp_path),
        )
        self._bankroll = BankrollManager(
            BankrollConfig(
                auto_reinvest_enabled=True,
                reinvest_rate_pct=50,
                base_borrow_amount_wei=1_000_000,
                max_borrow_amount_wei=0,
            )
        )
        self._market_regime = {"regime": "balanced"}
        self._internal_prime = None
        self._last_settlement_sync = {}


def _flashloan_pending() -> dict:
    return {
        "strategy_family": "flashloan_atomic",
        "route_family": "flashloan_atomic",
        "flashloan_fee_wei": "4500",
        "borrow_cost_usd": 1.25,
        "capture_meta": {
            "lane": "PRIVATE",
            "metadata": {
                "flashloan_resilience": {
                    "selected_provider": "aave",
                    "fallback_provider": "balancer",
                    "provider_priority": ["aave", "balancer"],
                    "sizing": {
                        "borrow_mult": 1.4,
                        "size_mult": 1.1,
                        "borrowCostUsd": 1.25,
                        "provider_choice_reason": "deepest_liquidity",
                    },
                }
            },
        },
    }


def test_flashloan_pending_operator_reflection():
    runtime = _FlashloanLiveRuntime()
    svc = ExecutionService()

    live = svc.build_live_state(runtime)
    item = live["items"][0]
    assert item["flashloan"]["selectedProvider"] == "aave"
    assert item["flashloan"]["flashloanFeeWei"] == 4500
    assert item["flashloan"]["borrowCostUsd"] == 1.25

    summary = svc.summarize(runtime)
    assert summary["lastProvider"] == "aave"
    assert summary["lastFlashloanFeeWei"] == 4500
    assert summary["lastBorrowCostUsd"] == 1.25


def test_flashloan_settlement_accounting_and_operator_reflection(tmp_path: Path):
    runtime = _FlashloanSettlementRuntime(tmp_path)
    runtime._bankroll.record_trade(
        success=True, realized_profit_after_gas_wei=6_000_000, amount_in_wei=1_500_000
    )

    out = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xflash",
        pending=_flashloan_pending(),
        decoded={
            "realized_profit_after_gas_wei": "6000000",
            "realized_profit_after_gas_usd_micro": "6000000",
            "realized_gas_cost_wei": "200000",
            "realized_gas_cost_usd_micro": "1000000",
        },
        status=1,
        amount_in=1_500_000,
        expected_after=7_000_000,
        realized_after=6_000_000,
        submit_to_receipt_ms=420,
        route_id="route-flash",
        route_family="flashloan_atomic",
        strategy_family="flashloan_atomic",
        capture_lane_pending="PRIVATE",
    )

    assert out["ok"] is True
    assert out["loanSettlement"] == {}
    assert out["borrowing"]["source"] == "flashloan"
    assert out["borrowing"]["provider"] == "aave"
    assert out["borrowing"]["flashloanFeeWei"] == 4500
    assert out["borrowing"]["borrowCostUsd"] == 1.25
    assert out["borrowing"]["amountInWei"] == 1_500_000

    tx_rows = runtime._ledger.transactions_tail(limit=5)
    assert len(tx_rows) == 1
    tx_meta = tx_rows[0]["metadata"]
    assert tx_meta["borrow_cost_usd"] == 1.25
    assert tx_meta["profitabilityChain"]["realizedAfterGasWei"] == "6000000"
    assert runtime._ledger.balance_report()["balances"]["USD"] == 4.75
    assert runtime._ledger_repo.transaction_balance_report(chain="eth")["balances"]["USD"] == 4.75
    tail = runtime._ledger.tail(limit=5)
    borrow_cost = next(row for row in tail if row["entry_type"] == "borrow_cost")
    assert borrow_cost["metadata"]["settlementRole"] == "borrow_cost"
    assert borrow_cost["metadata"]["profitabilityChain"]["realizedAfterGasWei"] == "6000000"
    assert any(row["entry_type"] == "borrow_cost" for row in tail)
    assert any(row["entry_type"] == "realized_pnl" for row in tail)

    ledger_state = AuxiliaryStateService().ledger_state(runtime)
    assert ledger_state["lastSettlement"]["borrowing"]["source"] == "flashloan"
    assert ledger_state["lastSettlement"]["borrowing"]["provider"] == "aave"
    assert int(str(ledger_state["lastSettlement"]["borrowing"]["flashloanFeeWei"])) == 4500

    meta = runtime._treasury.cfg.meta
    assert meta["last_settlement_borrowing_source"] == "flashloan"
    assert meta["last_settlement_flashloan_provider"] == "aave"
    assert meta["last_settlement_flashloan_fee_wei"] == 4500


def test_flashloan_settlement_blocks_when_outcome_truth_is_unverified(tmp_path: Path):
    runtime = _FlashloanSettlementRuntime(tmp_path)

    out = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xflash-gap",
        pending=_flashloan_pending(),
        decoded={
            "realized_profit_after_gas_wei": "0",
            "realized_profit_after_gas_usd_micro": "0",
            "realized_gas_cost_wei": "200000",
            "realized_gas_cost_usd_micro": "1000000",
        },
        status=1,
        amount_in=1_500_000,
        expected_after=7_000_000,
        realized_after=0,
        submit_to_receipt_ms=420,
        route_id="route-flash-gap",
        route_family="flashloan_atomic",
        strategy_family="flashloan_atomic",
        capture_lane_pending="PRIVATE",
        outcome_truth_verified=False,
        outcome_truth_reason_code="settled_profit_truth_unavailable",
    )

    assert out["ok"] is False
    assert out["blockedAutoTrading"] is True
    assert out["reason_code"] == "settled_profit_truth_unavailable"
    assert runtime._auto_trading is False
    assert runtime.cfg.execution.auto_trading is False
    assert runtime._ledger.transactions_tail(limit=5) == []
    assert runtime._ledger_repo.all_transactions(chain="eth") == []
