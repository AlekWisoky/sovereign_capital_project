from victor_ai_bot.capital_demand import CapitalDemand, capital_demand_from_mapping


def test_capital_demand_preserves_requested_authorized_and_deployed_lineage():
    demand = capital_demand_from_mapping(
        {
            "requestedNotionalUsd": 125.0,
            "authorizedUsdMicro": 100_000_000,
            "deployedUsdMicro": 75_000_000,
            "authoritySource": "internal_prime",
            "capitalSource": "internal_prime",
            "goalPosture": "moderate",
            "authorizationReason": "ok",
        }
    )

    assert demand == CapitalDemand(
        requested_usd_micro=125_000_000,
        authorized_usd_micro=100_000_000,
        deployed_usd_micro=75_000_000,
        authority_source="internal_prime",
        capital_source="internal_prime",
        goal_posture="moderate",
        authorization_reason="ok",
    )


def test_capital_demand_never_invents_authorization_when_admission_denied():
    demand = capital_demand_from_mapping(
        {
            "requestedNotionalUsd": 50.0,
            "capitalAdmission": {
                "allowed": False,
                "reason_code": "deployable_capital_exceeded",
            },
        }
    )

    assert demand.requested_usd_micro == 50_000_000
    assert demand.authorized_usd_micro == 0
    assert demand.deployed_usd_micro == 0
    assert demand.authorization_reason == "deployable_capital_exceeded"
