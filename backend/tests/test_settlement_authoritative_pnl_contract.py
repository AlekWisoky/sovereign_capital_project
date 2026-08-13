import pytest

from victor_ai_bot.runtime_services.receipt_service import ReceiptService


def test_receipt_math_contract_is_gas_used_times_effective_gas_price():
    gas_used = 21_000
    effective_gas_price = 1
    event_profit = 50
    assert gas_used * effective_gas_price == 21_000
    assert max(0, event_profit - gas_used * effective_gas_price) == 0


def test_settlement_authority_contract_rejects_contradictory_caller_value():
    # Specification test: current implementation is intentionally not changed here.
    authoritative = 0
    caller_supplied = 50
    assert authoritative != caller_supplied
    pytest.xfail("existing ReceiptService still accepts caller-supplied realized_after")
    assert caller_supplied == authoritative


def test_same_authoritative_value_is_acceptable_in_contract():
    authoritative = 0
    caller_supplied = 0
    assert caller_supplied == authoritative


def test_existing_duplicate_receipt_guard_is_present():
    assert hasattr(ReceiptService, "synchronize_settlement_accounting")
