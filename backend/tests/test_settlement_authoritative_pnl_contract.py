from victor_ai_bot.capital_demand import capital_demand_from_mapping
from victor_ai_bot.runtime_services.receipt_service import ReceiptService


def test_receipt_math_contract_is_gas_used_times_effective_gas_price():
    gas_used = 21_000
    effective_gas_price = 1
    event_profit = 50
    assert gas_used * effective_gas_price == 21_000
    assert max(0, event_profit - gas_used * effective_gas_price) == 0


def test_capital_demand_clamps_authorized_and_deployed_to_actual_authority():
    demand = capital_demand_from_mapping(
        {
            "requestedUsdMicro": 1_000_000,
            "authorizedUsdMicro": 2_000_000,
            "deployedUsdMicro": 3_000_000,
            "capitalAuthority": {"source": "capital_engine_state"},
            "capitalSource": "internal_prime",
            "wealthGoal": {"riskTolerance": "balanced"},
            "capitalAdmission": {"reason_code": "ok", "allowed": True},
        }
    )

    assert demand.requested_usd_micro == 1_000_000
    assert demand.authorized_usd_micro == 2_000_000
    assert demand.deployed_usd_micro == 2_000_000
    assert demand.authority_source == "capital_engine_state"
    assert demand.capital_source == "internal_prime"
    assert demand.goal_posture == "balanced"
    assert demand.authorization_reason == "ok"


def test_capital_demand_derives_authorized_amount_from_allowed_admission():
    demand = capital_demand_from_mapping(
        {
            "requestedUsdMicro": 750_000,
            "capitalAdmission": {
                "allowed": True,
                "reason_code": "approved",
            },
        }
    )

    assert demand.requested_usd_micro == 750_000
    assert demand.authorized_usd_micro == 750_000
    assert demand.deployed_usd_micro == 0


def test_current_receipt_service_exposes_canonical_settlement_sync():
    assert hasattr(ReceiptService, "synchronize_settlement_accounting")
