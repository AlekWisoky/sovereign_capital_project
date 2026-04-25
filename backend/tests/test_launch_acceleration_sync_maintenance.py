from __future__ import annotations

from victor_ai_bot.fund_os.family_readiness import build_family_readiness
from victor_ai_bot.fund_os.health_states import HealthState
from victor_ai_bot.fund_os.staged_rollout import StagedRolloutManager


BASE_SUMMARY = {
    "fundStage": "pilot_capital",
    "capitalReady": True,
    "internalPrimeReady": True,
    "privateRoutingReady": True,
    "receiptOutcomeTruthFreshnessClass": "current",
    "receiptOutcomeTruthFreshnessReasonCodes": [],
    "receiptOutcomeTruthReliabilityClass": "stable",
    "receiptOutcomeTruthReliabilityReasonCode": "ok",
    "receiptOutcomeTruthReliabilityReasonCodes": [],
}


def test_family_readiness_requires_realized_execution_evidence_before_launch_acceleration():
    readiness = build_family_readiness(
        family="funding_arb",
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "funding_arb",
                    "count": 2,
                    "executionSuccessRate": 0.9,
                    "gasEfficiency": 1.5,
                }
            ]
        },
        engine_state={
            "summary": {"engines": [{"engine_type": "funding_arb", "mode": "capped_live"}]},
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 18.0},
                    "admission": {"allowed": True, "mode": "capped_live"},
                    "capture": {"action": "trade"},
                }
            ],
        },
        telemetry={"venueReliability": 0.9},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 1.0}
            ]
        },
        fund_summary=dict(BASE_SUMMARY),
        active_families=["flash_arb"],
        family_states={"funding_arb": "observe_only"},
        exploration_budget={"used_trades": 0, "max_trades": 3},
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert readiness["ready"] is False
    assert readiness["launchAccelerationSeedReady"] is False
    assert "insufficient_realized_execution_evidence" in readiness["launchAccelerationReasonCodes"]
    assert "insufficient_realized_execution_evidence" in readiness["blockers"]
    assert readiness["suggestedNextAction"] == "collect_live_execution_evidence"



def _recommendation_ctx() -> dict:
    return {
        "stage": "pilot_capital",
        "scorecards": {
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 3,
                    "executionSuccessRate": 0.9,
                    "gasEfficiency": 1.5,
                },
                {
                    "family": "cex_cex_arb",
                    "count": 9,
                    "executionSuccessRate": 0.9,
                    "gasEfficiency": 1.4,
                },
            ]
        },
        "engine_state": {
            "summary": {
                "engines": [
                    {"engine_type": "funding_arb", "mode": "capped_live"},
                    {"engine_type": "cex_cex_arb", "mode": "capped_live"},
                ]
            },
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 18.0},
                    "admission": {"allowed": True, "mode": "capped_live"},
                    "capture": {"action": "trade"},
                },
                {
                    "opportunity": {"strategy_family": "cex_cex_arb", "expected_profit_usd": 21.0},
                    "admission": {"allowed": True, "mode": "capped_live"},
                    "capture": {"action": "trade"},
                },
            ],
        },
        "telemetry": {"venueReliability": 0.9},
        "calibration": {
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 1.0},
                {"route_family": "cex_cex_arb", "lane": "PROTECTED", "calibration_factor": 1.0},
            ]
        },
        "fund_summary": dict(BASE_SUMMARY),
        "capital_state": {
            "capital_engine": {"family_targets": {"funding_arb": 0.2, "cex_cex_arb": 0.15}}
        },
    }



def test_recommendation_holds_expansion_until_active_secondary_is_stable(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    mgr.set_mode("STAGED_MULTI_STRATEGY")
    mgr.profile.active_families = ["flash_arb", "funding_arb"]
    mgr.profile.family_states["flash_arb"] = HealthState.LIVE.value
    mgr.profile.family_states["funding_arb"] = HealthState.CAPPED_LIVE.value
    rec = mgr.recommendation(**_recommendation_ctx())
    assert rec["recommended_next_family"] == ""
    assert rec["launch_acceleration_phase"] == "stabilize_active_multi_strategy"
    assert "funding_arb" in rec["launch_acceleration"]["unstableSecondaryFamilies"]
    assert "insufficient_multi_strategy_stability_evidence" in rec["launch_acceleration_reason_codes"]
    assert rec["launch_acceleration_next_action"] == "stabilize_active_family_before_expansion"
    assert rec["hold_reason_code"] == "insufficient_multi_strategy_stability_evidence"



def test_recommendation_surfaces_specific_launch_acceleration_reason_for_sparse_candidate(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {"family": "flash_arb", "count": 20, "executionSuccessRate": 0.92, "gasEfficiency": 4.0},
                {"family": "funding_arb", "count": 2, "executionSuccessRate": 0.95, "gasEfficiency": 1.2},
            ]
        },
        engine_state={
            "summary": {"engines": [{"engine_type": "funding_arb", "mode": "capped_live"}]},
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 17.0},
                    "admission": {"allowed": True, "mode": "capped_live"},
                    "capture": {"action": "trade"},
                }
            ],
        },
        telemetry={"venueReliability": 0.9},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 1.0}
            ]
        },
        fund_summary=dict(BASE_SUMMARY),
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recommended_next_family"] == ""
    assert rec["blocked_families"]["funding_arb"] == "insufficient_realized_execution_evidence"
    assert rec["blocked_family_details"]["funding_arb"]["launch_acceleration_reason_codes"] == [
        "insufficient_realized_execution_evidence"
    ]
