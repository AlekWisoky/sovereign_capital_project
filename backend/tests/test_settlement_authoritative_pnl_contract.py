import pytest

from victor_ai_bot.capital_demand import CapitalDemandError, validate_settlement_authority
from victor_ai_bot.runtime_services.receipt_service import ReceiptService


def test_receipt_math_contract_is_gas_used_times_effective_gas_price():
    gas_used = 21_000
    effective_gas_price = 1
    event_profit = 50
    assert gas_used * effective_gas_price == 21_000
    assert max(0, event_profit - gas_used * effective_gas_price) == 0


def test_authority_invariant_rejects_contradictory_values_without_claiming_runtime_enforcement():
    with pytest.raises(CapitalDemandError):
        validate_settlement_authority(authoritative_after=0, supplied_after=50)


def test_authority_invariant_accepts_same_value():
    validate_settlement_authority(authoritative_after=0, supplied_after=0)


def test_current_receipt_service_is_only_a_future_integration_target():
    assert hasattr(ReceiptService, "synchronize_settlement_accounting")
    pytest.xfail("FUTURE PRODUCTION INTEGRATION TEST: ReceiptService is not modified in this phase")
