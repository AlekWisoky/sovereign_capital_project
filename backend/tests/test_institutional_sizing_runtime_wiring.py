from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.capital_admission_service import PreTradeCapitalAdmission
from victor_ai_bot.runtime_services.institutional_sizing_runtime import (
    InstitutionalSizingAdmissionService,
)


# This slice verifies context/lineage wiring only; canonical admission remains authoritative.
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
        cfg=SimpleNamespace(execution=SimpleNamespace(live_authority=False)),
    )


def _opp():
    return SimpleNamespace(
        id="opp-runtime-1",
        route_id="route-runtime-1",
        meta={
            "strategy_family": "flash_arb",
            "entry_notional_usd": 250_000.0,
            "margin_ratio": 0.04,
            "capture": {
                "metadata": {
                    "depth_usd": 600_000.0,
                    "pool_depth_cap_usd": 500_000.0,
                    "simulation_confidence": 0.92,
                    "freshness_score": 0.95,
                    "venue_reliability_score": 0.90,
                    "endpoint_selection": {
                        "pipeline_latency_ms": 250.0,
                        "pressure": 0.15,
                        "endpoint_quality": 0.90,
                    },
                }
            },
            "unit_econ": {"entry_notional_usd": 250_000.0},
        },
        confidence=0.92,
        expected_profit_usd=120.0,
    )


def _admitted_result():
    return PreTradeCapitalAdmission(
        allowed=True,
        reason_code="ok",
        strategy_family="flash_arb",
        capital_source="flashloan",
        requested_notional_usd=250_000.0,
        projected_realized_edge_usd=120.0,
        confidence=0.92,
        details={},
    )


def test_runtime_adapter_materializes_authoritative_capital_and_prime_context(monkeypatch):
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.institutional_sizing_runtime.CapitalAdmissionService.evaluate",
        lambda self, runtime, opp, decision=None: _admitted_result(),
    )

    result = InstitutionalSizingAdmissionService().evaluate(
        _runtime(), _opp(), decision=SimpleNamespace(size_mult=1.0, borrow_mult=1.0)
    )

    record = result.details["institutionalSizing"]
    assert record["valid"] is True
    contract = record["contract"]
    assert contract["capital"]["source"] == "capital_engine_state"
    assert contract["capital"]["authority_id"] == "cap-auth-runtime"
    assert contract["capital"]["prime_available"] is True
    assert contract["capital"]["prime_capacity_usd"] == 10_000_000.0
    assert contract["requested_notional_usd"] == 250_000.0
    assert record["behavior_change"] == "none"


def test_runtime_adapter_does_not_replace_existing_admission_result(monkeypatch):
    expected = _admitted_result()
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.institutional_sizing_runtime.CapitalAdmissionService.evaluate",
        lambda self, runtime, opp, decision=None: expected,
    )

    result = InstitutionalSizingAdmissionService().evaluate(_runtime(), _opp())

    assert result.allowed is expected.allowed
    assert result.reason_code == expected.reason_code
    assert result.strategy_family == expected.strategy_family
    assert result.capital_source == expected.capital_source
    assert result.requested_notional_usd == expected.requested_notional_usd
