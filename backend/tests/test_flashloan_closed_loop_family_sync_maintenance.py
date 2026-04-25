from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade

from tests.test_flashloan_borrowing_lifecycle_proof import (
    _FlashloanLiveRuntime,
    _FlashloanSettlementRuntime,
    _flashloan_pending,
)
from tests.test_receipt_terminal_profitability_chain import _authority


class _FollowthroughFacade(RuntimeReceiptFacade):
    def __init__(self):
        self._last_settlement_sync = {
            "ok": True,
            "receiptId": "0xsettle",
            "status": "settled",
        }


def test_execution_summary_exposes_canonical_pending_family_identity() -> None:
    runtime = _FlashloanLiveRuntime()

    summary = ExecutionService().summarize(runtime)

    assert summary["lastRouteFamily"] == "flashloan_atomic"
    assert summary["lastFamily"] == "flash_arb"
    assert summary["lastRuntimeFamily"] == "flashloan_atomic"
    assert summary["lastCapitalFamily"] == "flashloan_atomic"
    assert summary["lastDisplayFamily"] == "Flash Arbitrage"
    assert "flashloan_atomic" in summary["lastFamilyAliases"]
    assert summary["lastFamilyIdentity"]["launchFamily"] == "flash_arb"


def test_receipt_summary_prefers_settlement_family_identity_and_closed_loop(tmp_path: Path) -> None:
    runtime = _FlashloanSettlementRuntime(tmp_path)
    runtime._last_settlement_sync = {
        "ok": True,
        "receiptId": "0xsettle",
        "status": "settled",
        "routeFamily": "flashloan_atomic",
        "family": "flash_arb",
        "runtimeFamily": "flashloan_atomic",
        "capitalFamily": "flashloan_atomic",
        "displayFamily": "Flash Arbitrage",
        "familyAliases": ["flash_arb", "flashloan_atomic"],
        "familyIdentity": {
            "requestedFamily": "flashloan_atomic",
            "launchFamily": "flash_arb",
            "runtimeFamily": "flashloan_atomic",
            "capitalFamily": "flashloan_atomic",
            "displayName": "Flash Arbitrage",
            "aliases": ["flash_arb", "flashloan_atomic"],
            "isCore": True,
        },
        "borrowing": {
            "source": "flashloan",
            "provider": "aave",
            "flashloanFeeWei": 4500,
            "borrowCostUsd": 1.25,
        },
        "loanSettlement": {},
        "learningSync": {"executed": True, "ok": True, "reasonCode": "ok"},
        "memorySync": {"executed": True, "ok": True, "reasonCode": "ok"},
        "closedLoop": {
            "settlementAccounting": True,
            "learningRecorded": True,
            "memoryRecorded": True,
            "completed": True,
            "reasonCodes": [],
            "nextAction": "none",
        },
        "terminalProfitabilityAuthority": _authority(),
        "capitalAdmission": {"allowed": True, "reason_code": "ok", "details": {}},
    }
    runtime.execution_live_state = lambda: {"items": []}

    summary = ReceiptService().summarize(runtime)

    assert summary["lastTxHash"] == "0xsettle"
    assert summary["lastRouteFamily"] == "flashloan_atomic"
    assert summary["lastFamily"] == "flash_arb"
    assert summary["lastRuntimeFamily"] == "flashloan_atomic"
    assert summary["lastCapitalFamily"] == "flashloan_atomic"
    assert summary["lastProvider"] == "aave"
    assert summary["lastFlashloanFeeWei"] == 4500
    assert summary["lastBorrowCostUsd"] == 1.25
    assert summary["lastClosedLoop"]["completed"] is True
    assert summary["lastLearningSync"]["ok"] is True
    assert summary["lastMemorySync"]["ok"] is True


def test_settlement_accounting_emits_family_identity_and_pending_closed_loop(tmp_path: Path) -> None:
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

    assert out["family"] == "flash_arb"
    assert out["runtimeFamily"] == "flashloan_atomic"
    assert out["capitalFamily"] == "flashloan_atomic"
    assert out["familyIdentity"]["launchFamily"] == "flash_arb"
    assert out["closedLoop"]["settlementAccounting"] is True
    assert out["closedLoop"]["completed"] is False
    assert out["closedLoop"]["nextAction"] == "finalize_receipt_followthrough"


def test_runtime_receipt_facade_updates_closed_loop_followthrough_state() -> None:
    facade = _FollowthroughFacade()

    facade._update_settlement_followthrough(learning_ok=True)
    assert facade._last_settlement_sync["learningSync"]["ok"] is True
    assert facade._last_settlement_sync["closedLoop"]["completed"] is False

    facade._update_settlement_followthrough(memory_ok=True)
    assert facade._last_settlement_sync["memorySync"]["ok"] is True
    assert facade._last_settlement_sync["closedLoop"]["completed"] is True
    assert facade._last_settlement_sync["closedLoop"]["nextAction"] == "none"
