from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.institutional_sizing_runtime import (
    InstitutionalSizingAdmissionService,
)


def _runtime():
    return SimpleNamespace(
        capital_engine_state=lambda: {
            "status": "ok",
            "freshness_class": "fresh",
            "authority_id": "cap-auth-runtime",
            "deployable_usd": 2_000_000.0,
        },
        _internal_prime=SimpleNamespace(
            snapshot=lambda: {
                "stateReady": True,
                "capacityUsd": 10_000_000.0,
                "utilization": 0.10,
                "reservedCollateralUsd": 0.0,
                "familyExposure": {"flash_arb": 0.0},
            }
        ),
        _wealth_goal_service=SimpleNamespace(
            snapshot=lambda: {
                "targetReturnPct": 9.0,
                "currentReturnPct": 3.0,
                "capitalCommitmentPct": 25.0,
                "aggressivenessCap": 1.0,
                "maxDrawdownPct": 10.0,
                "drawdownPct": 1.0,
                "timeframeDays": 30,
                "goalStatus": "active",
            }
        ),
    )


def _opp():
    return SimpleNamespace(
        id="opp-runtime-1",
        route_id="route-runtime-1",
        meta={
            "strategy_family": "flash_arb",
            "entry_notional_usd": 250_000.0,
            "asset_price_usd": 1.0,
            "capture": {
                "metadata": {
                    "depth_usd": 600_000.0,
                    "pool_depth_cap_usd": 500_000.0,
                    "simulation_confidence": 0.92,
                    "freshness_score": 0.95,
                    "venue_reliability_score": 0.90,
                    "endpoint_selection": {
                        "measured_latency_ms": 250.0,
                        "pressure": 0.15,
                        "endpoint_quality": 0.90,
                    },
                }
            },
            "unit_econ": {
                "entry_notional_usd": 250_000.0,
            },
        },
        confidence=0.92,
        expected_profit_usd=120.0,
    )


def test_runtime_adapter_attaches_institutional_contract_without_replacing_admission_authority():
    service = InstitutionalSizingAdmissionService()
    runtime = _runtime()
    opp = _opp()

    # Use the existing admission implementation as the authority. The adapter
    # only materializes the typed Phase-B contract after admission evaluation.
    result = service.evaluate(runtime, opp, decision=SimpleNamespace(size_mult=1.0, borrow_mult=1.0))

    contract_record = result.details["institutionalSizing"]
    assert contract_record["valid"] is True
    contract = contract_record["contract"]
    assert contract["capital"]["source"] == "capital_engine_state"
    assert contract["capital"]["authority_id"] == "cap-auth-runtime"
    assert contract["capital"]["prime_available"] is True
    assert contract["capital"]["prime_capacity_usd"] == 10_000_000.0
    assert contract["requested_notional_usd"] == result.requested_notional_usd
    assert contract_record["behavior_change"] == "none"


def test_runtime_adapter_preserves_existing_admission_result():
    service = InstitutionalSizingAdmissionService()
    runtime = _runtime()
    opp = _opp()
    decision = SimpleNamespace(size_mult=1.0, borrow_mult=1.0)

    result = service.evaluate(runtime, opp, decision=decision)

    assert result.strategy_family == "flash_arb"
    assert result.capital_source == "flashloan"
    assert result.requested_notional_usd == 250_000.0
    assert result.projected_realized_edge_usd >= 0.0
    assert result.details["institutionalSizing"]["behavior_change"] == "none"
