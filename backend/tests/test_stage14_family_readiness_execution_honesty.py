from __future__ import annotations

from victor_ai_bot.fund_os.family_readiness import build_family_readiness


BASE_KWARGS = {
    "stage": "private_fund",
    "scorecards": {
        "families": [
            {
                "family": "funding_arb",
                "count": 8,
                "executionSuccessRate": 0.75,
                "gasEfficiency": 2.5,
                "drawdownPenalty": 0.0,
                "competitionPressure": 0.1,
            }
        ]
    },
    "engine_state": {
        "summary": {"engines": [{"engine_type": "funding_arb", "mode": "live"}]},
        "items": [
            {
                "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 42.0},
                "admission": {"allowed": True, "mode": "capped_live"},
                "capture": {"action": "trade"},
            }
        ],
    },
    "telemetry": {"venueReliability": 0.8},
    "calibration": {"items": [{"route_family": "funding", "calibration_factor": 0.9}]},
    "fund_summary": {
        "capitalReady": True,
        "internalPrimeReady": True,
        "privateRoutingReady": True,
        "receiptOutcomeTruthFreshnessClass": "current",
        "receiptOutcomeTruthFreshnessReasonCodes": [],
        "receiptOutcomeTruthReliabilityClass": "stable",
        "receiptOutcomeTruthReliabilityReasonCode": "ok",
        "receiptOutcomeTruthReliabilityReasonCodes": [],
    },
    "active_families": ["flash_arb"],
    "family_states": {"funding_arb": "observe_only"},
    "exploration_budget": {"used_trades": 0, "max_trades": 3},
}


def test_family_readiness_flags_execution_evidence_that_is_not_live_ready():
    readiness = build_family_readiness(
        family="funding_arb",
        engine_state={
            "summary": {"engines": [{"engine_type": "funding_arb", "mode": "live"}]},
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 42.0},
                    "admission": {"allowed": True, "mode": "observe_only"},
                    "capture": {"action": "drop", "drop_reason": "insufficient_confidence"},
                }
            ],
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "engine_state"},
    )
    assert readiness["executionEvidencePresent"] is True
    assert readiness["actualExecutionReady"] is False
    assert "execution_not_ready" in readiness["blockers"]
    assert readiness["executionReasons"]


def test_flash_arb_reports_live_execution_readiness():
    readiness = build_family_readiness(
        family="flash_arb",
        stage="private_fund",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.9,
                    "gasEfficiency": 3.0,
                    "drawdownPenalty": 0.0,
                    "competitionPressure": 0.1,
                }
            ]
        },
        engine_state={
            "summary": {"engines": [{"engine_type": "flash_arb", "mode": "live"}]},
            "items": [],
        },
        telemetry={"venueReliability": 0.9},
        calibration={"items": [{"route_family": "flashloan_atomic", "calibration_factor": 1.0}]},
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
        },
        active_families=["flash_arb"],
        family_states={"flash_arb": "live"},
        exploration_budget={"used_trades": 0, "max_trades": 3},
    )
    assert readiness["executionEvidencePresent"] is True
    assert readiness["actualExecutionReady"] is True
    assert readiness["executionMode"] == "live"


def test_family_readiness_blocks_non_core_family_without_execution_evidence():
    readiness = build_family_readiness(
        family="funding_arb",
        engine_state={"summary": {"engines": []}, "items": []},
        **{k: v for k, v in BASE_KWARGS.items() if k != "engine_state"},
    )
    assert readiness["executionEvidencePresent"] is False
    assert readiness["actualExecutionReady"] is False
    assert readiness["ready"] is False
    assert "no_execution_evidence" in readiness["blockers"]
    assert readiness["suggestedNextAction"] == "collect_live_execution_evidence"


def test_family_readiness_blocks_non_core_family_when_receipt_truth_is_not_rollout_ready():
    readiness = build_family_readiness(
        family="funding_arb",
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
            "receiptOutcomeTruthFreshnessClass": "unavailable",
            "receiptOutcomeTruthFreshnessReasonCodes": ["receipt_outcome_truth_freshness_unavailable"],
            "receiptOutcomeTruthReliabilityClass": "unavailable",
            "receiptOutcomeTruthReliabilityReasonCode": "receipt_outcome_truth_reliability_unavailable",
            "receiptOutcomeTruthReliabilityReasonCodes": ["receipt_outcome_truth_reliability_unavailable"],
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert readiness["ready"] is False
    assert readiness["receiptOutcomeTruthRolloutReady"] is False
    assert readiness["receiptOutcomeTruthRolloutReasonCodes"] == [
        "receipt_outcome_truth_freshness_unavailable",
        "receipt_outcome_truth_reliability_unavailable",
    ]
    assert "receipt_outcome_truth_freshness_unavailable" in readiness["blockers"]
    assert readiness["suggestedNextAction"] == "restore_receipt_outcome_truth"
