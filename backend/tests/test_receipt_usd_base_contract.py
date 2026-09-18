from __future__ import annotations

from victor_ai_bot.runtime_services.receipt_service import ReceiptService


def test_base_receipt_service_never_infers_usd_from_raw_wei():
    assert ReceiptService._realized_after_usd(
        {"realized_profit_after_gas_wei": "6000000"}, status=1
    ) == 0.0


def test_base_receipt_service_uses_explicit_usd_observation():
    assert ReceiptService._realized_after_usd(
        {"realized_profit_after_gas_usd_micro": "1250000"}, status=1
    ) == 1.25
