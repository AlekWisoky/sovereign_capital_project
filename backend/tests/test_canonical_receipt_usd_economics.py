from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.canonical_receipt_service import CanonicalReceiptService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


def test_successful_receipt_requires_explicit_usd_truth() -> None:
    svc = CanonicalReceiptService()

    truth = svc.settled_outcome_truth(
        status=1,
        decoded={
            "realized_profit_after_gas_wei": "6000000",
            "realized_profit_token": "WETH",
            "realized_profit_token_wei": "6000000",
        },
    )

    assert truth["ok"] is False
    assert truth["verified"] is False
    assert truth["reason_code"] == "settled_usd_truth_unavailable"


def test_successful_receipt_accepts_explicit_usd_truth() -> None:
    svc = CanonicalReceiptService()

    truth = svc.settled_outcome_truth(
        status=1,
        decoded={"realized_profit_after_gas_usd_micro": "1250000"},
    )

    assert truth["ok"] is True
    assert truth["verified"] is True
    assert truth["reason_code"] == "ok"


def test_realized_usd_never_falls_back_to_raw_wei() -> None:
    svc = CanonicalReceiptService()

    assert svc._realized_after_usd(
        {"realized_profit_after_gas_wei": "6000000"}, status=1
    ) is None
    assert svc._realized_after_usd(
        {"realized_profit_after_gas_usd_micro": "1250000"}, status=1
    ) == 1.25


def test_settlement_accounting_blocks_without_explicit_usd_truth() -> None:
    svc = CanonicalReceiptService()
    runtime = SimpleNamespace()

    result = svc.synchronize_settlement_accounting(
        runtime,
        tx_hash="0xreceipt",
        pending={},
        decoded={"realized_profit_after_gas_wei": "6000000"},
        status=1,
        amount_in=1000,
        expected_after=500,
        realized_after=6000000,
        submit_to_receipt_ms=10,
        route_id="route-1",
        route_family="flashloan_atomic",
        strategy_family="flashloan_atomic",
        capture_lane_pending="PRIVATE",
    )

    assert result["ok"] is False
    assert result["blockedAutoTrading"] is True
    assert result["reason_code"] == "settled_usd_truth_unavailable"
    assert runtime._last_settlement_sync["reason_code"] == "settled_usd_truth_unavailable"


# The runtime facade must consume explicit USD micro-units only; raw wei is never a USD source.
def test_runtime_receipt_facade_accepts_explicit_usd_and_rejects_wei_only():
    explicit = RuntimeReceiptFacade._explicit_usd_economics(
        {"realized_profit_after_gas_usd_micro": "1250000", "realized_profit_after_gas_wei": "6000000"},
        {"terminal_profitability_authority": {"profitability": {"profit_after_costs_usd_micro": "2500000"}}},
    )
    assert explicit == (1.25, 2.5)

    wei_only = RuntimeReceiptFacade._explicit_usd_economics(
        {"realized_profit_after_gas_wei": "6000000"},
        {"expected_after": "2500000"},
    )
    assert wei_only == (None, None)


def test_base_receipt_service_never_infers_usd_from_wei():
    assert ReceiptService._realized_after_usd(
        {"realized_profit_after_gas_wei": "6000000"},
        status=1,
    ) is None


def test_base_receipt_service_requires_explicit_usd_for_settlement_truth():
    assert ReceiptService().settled_outcome_truth(
        status=1,
        decoded={"realized_profit_after_gas_wei": "6000000"},
    )["verified"] is False
