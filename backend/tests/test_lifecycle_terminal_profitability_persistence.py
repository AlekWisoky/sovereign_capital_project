from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.strategies.lifecycle_history import StrategyLifecycleMemory
from victor_ai_bot.treasury.ledger import TreasuryLedger


class _Runtime:
    def __init__(self, tmp_path):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="eth"), execution=SimpleNamespace(auto_trading=True)
        )
        self._auto_trading = True
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
        self._ledger_repo = None
        self._treasury = None
        self._internal_prime = None
        self._market_regime = {"regime": "balanced"}
        self._bankroll = BankrollManager(
            BankrollConfig(
                auto_reinvest_enabled=True,
                reinvest_rate_pct=50,
                base_borrow_amount_wei=1_000_000,
                max_borrow_amount_wei=0,
            )
        )
        self._lifecycle_memory = StrategyLifecycleMemory(
            str(tmp_path / "strategies" / "lifecycle.json"), chain="eth"
        )


def test_receipt_sync_persists_terminal_profitability_in_lifecycle_memory(tmp_path):
    runtime = _Runtime(tmp_path)
    runtime._bankroll.record_trade(
        success=True, realized_profit_after_gas_wei=6_000_000, amount_in_wei=1_500_000
    )
    svc = ReceiptService()
    pending = {
        "strategy_family": "flashloan_atomic",
        "route_family": "flashloan_atomic",
        "terminal_profitability_authority": {
            "stage": "execution_preflight_gate",
            "reason": "profit_positive",
            "authoritative": True,
            "live_gas_derived": True,
            "profitability": {"profit_after_costs_wei": "6000000"},
        },
        "capital_admission": {"ok": True, "reason": "approved", "details": {}},
    }
    svc.synchronize_settlement_accounting(
        runtime,
        tx_hash="0xlife",
        pending=pending,
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
        route_id="route-life",
        route_family="flashloan_atomic",
        strategy_family="flashloan_atomic",
        capture_lane_pending="PRIVATE",
    )
    svc.observe_settlement_memory(
        runtime,
        pending=pending,
        status=1,
        submit_to_receipt_ms=420,
        realized_usd=6.0,
        expected_usd=7.0,
        gas_est_wei=200000,
        route_family="flashloan_atomic",
        strategy_family="flashloan_atomic",
        route_id="route-life",
        tx_hash="0xlife",
        capture_lane_pending="PRIVATE",
        capture_relay_pending="",
    )
    snap = runtime._lifecycle_memory.snapshot(family="flashloan_atomic")
    item = snap["items"][0]
    assert item["reason_code"] == "settled_success"
    assert item["payload"]["terminalProfitabilityAuthority"]["stage"] == "execution_preflight_gate"
    assert item["payload"]["profitabilityChain"]["realizedAfterGasWei"] == "6000000"
