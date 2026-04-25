from victor_ai_bot.fund_os.health_states import HealthState
from victor_ai_bot.fund_os.staged_rollout import StagedRolloutManager


def _ctx():
    return {
        "stage": "pilot_capital",
        "scorecards": {
            "families": [
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
            ]
        },
        "engine_state": {
            "summary": {"engines": [{"engine_type": "funding_arb", "mode": "capped_live"}]},
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 18.0},
                    "admission": {"allowed": True, "mode": "capped_live"},
                    "capture": {"action": "trade"},
                }
            ],
        },
        "telemetry": {},
        "calibration": {
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        "fund_summary": {
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": True,
            "internalPrimeReady": True,
            "receiptOutcomeTruthFreshnessClass": "current",
            "receiptOutcomeTruthFreshnessReasonCodes": [],
            "receiptOutcomeTruthReliabilityClass": "stable",
            "receiptOutcomeTruthReliabilityReasonCode": "ok",
            "receiptOutcomeTruthReliabilityReasonCodes": [],
        },
    }


def test_family_enable_enters_capped_live(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    mgr.set_mode("STAGED_MULTI_STRATEGY")
    out = mgr.enable_family("funding_arb", **_ctx())
    assert out["ok"] is True
    assert out["profile"]["family_states"]["funding_arb"] == HealthState.CAPPED_LIVE.value


def test_recommendation_blocks_rollout_when_execution_evidence_is_missing(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    ctx = _ctx()
    ctx["engine_state"] = {"summary": {"engines": []}, "items": []}
    rec = mgr.recommendation(**ctx)
    assert rec["recommended_next_family"] == ""
    assert rec["blocked_family_details"]["funding_arb"]["reason_code"] == "no_execution_evidence"
    assert rec["blocked_family_details"]["funding_arb"]["suggested_next_action"] == "collect_live_execution_evidence"


def test_quarantine_visible_in_recommendation(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    mgr.quarantine_family("funding_arb", reason_code="venue_unstable")
    rec = mgr.recommendation(**_ctx())
    item = next(x for x in rec["families"] if x["family"] == "funding_arb")
    assert item["status"] == "quarantined"
    assert item["degradedState"] == HealthState.QUARANTINED.value


def test_exploration_budget_enforced(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    mgr.set_mode("STAGED_MULTI_STRATEGY")
    mgr.profile.exploration_budget["max_trades"] = 0
    out = mgr.enable_family("funding_arb", **_ctx())
    assert out["ok"] is False
    assert out["reason_code"] == "exploration_budget_exhausted"


def test_recommendation_surfaces_specific_prime_truth_reason_codes_for_blocked_families(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": False,
            "internalPrimeReady": False,
            "capitalTruthReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
            "internalPrimeReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recommended_next_family"] == ""
    assert rec["blocked_families"]["funding_arb"] == "internal_prime_journal_borrowed_mismatch"
    assert (
        rec["blocked_family_details"]["funding_arb"]["suggested_next_action"]
        == "repair_internal_prime_accounting"
    )
    assert (
        rec["recommended_plan"]["why_not_others_details"]["funding_arb"]["reason_code"]
        == "internal_prime_journal_borrowed_mismatch"
    )


def test_recommendation_surfaces_top_level_hold_reason_for_global_execution_blockers(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": True,
            "internalPrimeReady": True,
            "drawdownState": {"hardStop": {"active": True, "reason_codes": ["drawdown_hard_stop"]}},
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recommended_next_family"] == ""
    assert rec["global_execution_blocked"] is True
    assert rec["global_execution_reason_codes"] == ["drawdown_hard_stop"]
    assert rec["hold_reason_code"] == "drawdown_hard_stop"
    assert rec["hold_reason_codes"][0] == "drawdown_hard_stop"
    assert rec["suggested_next_action"] == "reduce_drawdown_and_clear_hard_stop"
    assert rec["recommended_plan"]["hold_reason_code"] == "drawdown_hard_stop"
    assert rec["recommended_plan"]["suggested_next_action"] == "reduce_drawdown_and_clear_hard_stop"


def test_recommendation_surfaces_top_level_hold_reason_for_capital_truth_blockers(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": False,
            "internalPrimeReady": True,
            "capitalTruthReasonCodes": ["capital_truth_degraded"],
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recommended_next_family"] == ""
    assert rec["global_execution_blocked"] is False
    assert rec["capital_truth_reason_codes"] == ["capital_truth_degraded"]
    assert rec["hold_reason_code"] == "capital_truth_degraded"
    assert rec["suggested_next_action"] == "restore_capital_truth"
    assert rec["recommended_plan"]["hold_reason_codes"][0] == "capital_truth_degraded"


def test_recommendation_surfaces_recovery_canon_for_capital_truth_hold(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": False,
            "internalPrimeReady": True,
            "capitalTruthReasonCodes": ["capital_truth_unavailable"],
            "recoveryReady": False,
            "recoveryStatus": "capital_truth_restore_required",
            "recoveryReasonCode": "capital_truth_unavailable",
            "recoveryReasonCodes": ["capital_truth_unavailable"],
            "recoveryNextAction": "restore_capital_truth",
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recommended_next_family"] == ""
    assert rec["recovery_ready"] is False
    assert rec["recovery_status"] == "capital_truth_restore_required"
    assert rec["recovery_reason_code"] == "capital_truth_unavailable"
    assert rec["recovery_reason_codes"] == ["capital_truth_unavailable"]
    assert rec["recovery_next_action"] == "restore_capital_truth"
    assert (
        rec["blocked_family_details"]["funding_arb"]["recovery_status"]
        == "capital_truth_restore_required"
    )
    assert rec["blocked_family_details"]["funding_arb"]["recovery_reason_codes"] == [
        "capital_truth_unavailable"
    ]
    assert rec["recommended_plan"]["recovery_reason_code"] == "capital_truth_unavailable"
    assert rec["recommended_plan"]["recovery_next_action"] == "restore_capital_truth"


def test_recommendation_surfaces_recovery_freshness_canon_for_capital_truth_hold(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": False,
            "internalPrimeReady": True,
            "capitalTruthReasonCodes": ["capital_truth_unavailable"],
            "recoveryReady": False,
            "recoveryStatus": "capital_truth_restore_required",
            "recoveryReasonCode": "capital_truth_unavailable",
            "recoveryReasonCodes": ["capital_truth_unavailable"],
            "recoveryNextAction": "restore_capital_truth",
            "recoveryFreshnessClass": "unavailable",
            "recoveryFreshnessReasonCode": "capital_truth_freshness_unavailable",
            "recoveryFreshnessReasonCodes": ["capital_truth_freshness_unavailable"],
            "recoveryFreshnessNextAction": "refresh_capital_truth_snapshot",
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recovery_freshness_class"] == "unavailable"
    assert rec["recovery_freshness_reason_code"] == "capital_truth_freshness_unavailable"
    assert rec["recovery_freshness_reason_codes"] == ["capital_truth_freshness_unavailable"]
    assert rec["recovery_freshness_next_action"] == "refresh_capital_truth_snapshot"
    assert rec["blocked_family_details"]["funding_arb"]["recovery_freshness_reason_codes"] == [
        "capital_truth_freshness_unavailable"
    ]
    assert (
        rec["recommended_plan"]["recovery_freshness_reason_code"]
        == "capital_truth_freshness_unavailable"
    )


def test_recommendation_surfaces_recovery_history_canon_for_capital_truth_hold(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": False,
            "internalPrimeReady": True,
            "capitalTruthReasonCodes": ["capital_truth_unavailable"],
            "recoveryReady": False,
            "recoveryStatus": "capital_truth_restore_required",
            "recoveryReasonCode": "capital_truth_unavailable",
            "recoveryReasonCodes": ["capital_truth_unavailable"],
            "recoveryNextAction": "restore_capital_truth",
            "recoveryHistoryComponent": "capital_truth",
            "recoveryHistoryStatus": "degraded",
            "recoveryDegradedSinceTsMs": 1700000000000,
            "recoveryDegradedDurationMs": 60000,
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recovery_history_component"] == "capital_truth"
    assert rec["recovery_history_status"] == "degraded"
    assert rec["recovery_degraded_since_ts_ms"] == 1700000000000
    assert rec["blocked_family_details"]["funding_arb"]["recovery_history_status"] == "degraded"
    assert rec["recommended_plan"]["recovery_history_component"] == "capital_truth"


def test_recommendation_surfaces_recovery_history_count_and_severity_for_capital_truth_hold(
    tmp_path,
):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": False,
            "internalPrimeReady": True,
            "capitalTruthReasonCodes": ["capital_truth_unavailable"],
            "recoveryReady": False,
            "recoveryStatus": "capital_truth_restore_required",
            "recoveryReasonCode": "capital_truth_unavailable",
            "recoveryReasonCodes": ["capital_truth_unavailable"],
            "recoveryNextAction": "restore_capital_truth",
            "recoveryHistoryComponent": "capital_truth",
            "recoveryHistoryStatus": "degraded",
            "recoveryDegradedCount": 4,
            "recoveryLastHealthyTsMs": 1700000000000,
            "recoveryDegradationSeverityClass": "persistent",
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recovery_degraded_count"] == 4
    assert rec["recovery_last_healthy_ts_ms"] == 1700000000000
    assert rec["recovery_degradation_severity_class"] == "persistent"
    assert rec["blocked_family_details"]["funding_arb"]["recovery_degraded_count"] == 4


def test_recommendation_surfaces_recovery_reliability_canon_for_capital_truth_hold(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": False,
            "internalPrimeReady": True,
            "capitalTruthReasonCodes": ["capital_truth_unavailable"],
            "recoveryReady": False,
            "recoveryStatus": "capital_truth_restore_required",
            "recoveryReasonCode": "capital_truth_unavailable",
            "recoveryReasonCodes": ["capital_truth_unavailable"],
            "recoveryNextAction": "restore_capital_truth",
            "capitalTruthReliabilityClass": "unavailable",
            "capitalTruthReliabilityReasonCode": "capital_truth_reliability_unavailable",
            "capitalTruthReliabilityReasonCodes": [
                "capital_truth_reliability_unavailable",
                "capital_truth_freshness_unavailable",
            ],
            "recoveryReliabilityClass": "unavailable",
            "recoveryReliabilityReasonCode": "recovery_reliability_unavailable",
            "recoveryReliabilityReasonCodes": [
                "recovery_reliability_unavailable",
                "capital_truth_reliability_unavailable",
            ],
            "recoveryReliabilityNextAction": "restore_capital_truth",
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recovery_reliability_class"] == "unavailable"
    assert rec["recovery_reliability_reason_code"] == "recovery_reliability_unavailable"
    assert rec["recovery_reliability_next_action"] == "restore_capital_truth"
    assert (
        rec["blocked_family_details"]["funding_arb"]["recovery_reliability_reason_code"]
        == "recovery_reliability_unavailable"
    )
    assert rec["recommended_plan"]["recovery_reliability_class"] == "unavailable"


def test_recommendation_blocks_rollout_when_recovery_reliability_is_fragile_after_recent_recovery(
    tmp_path,
):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={
            "summary": {"engines": [{"engine_type": "funding_arb", "mode": "live"}]},
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 42.0},
                    "admission": {"allowed": True, "mode": "capped_live"},
                    "capture": {"action": "trade"},
                }
            ],
        },
        telemetry={"venueReliability": 0.8},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": True,
            "internalPrimeReady": True,
            "recoveryReady": True,
            "recoveryStatus": "ready",
            "recoveryReliabilityClass": "fragile",
            "recoveryReliabilityReasonCode": "recovery_reliability_fragile",
            "recoveryReliabilityReasonCodes": [
                "recovery_reliability_fragile",
                "recovery_recovered_fragile",
            ],
            "recoveryReliabilityNextAction": "repair_internal_prime_accounting",
            "recoveryRecoveredFragile": True,
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recommended_next_family"] == ""
    assert rec["hold_reason_code"] == "recovery_reliability_fragile"
    assert "recovery_reliability_fragile" in rec["hold_reason_codes"]
    assert rec["suggested_next_action"] == "repair_internal_prime_accounting"
    assert rec["blocked_family_details"]["funding_arb"]["recovery_reliability_class"] == "fragile"
    assert (
        rec["blocked_family_details"]["funding_arb"]["reason_code"]
        == "recovery_reliability_fragile"
    )
    assert (
        "recovery_reliability_fragile" in rec["blocked_family_details"]["funding_arb"]["blocked_by"]
    )


def test_recommendation_surfaces_receipt_outcome_truth_canon_for_capital_truth_hold(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain="eth")
    rec = mgr.recommendation(
        stage="pilot_capital",
        scorecards={
            "families": [
                {
                    "family": "flash_arb",
                    "count": 20,
                    "executionSuccessRate": 0.92,
                    "gasEfficiency": 4.0,
                },
                {
                    "family": "funding_arb",
                    "count": 9,
                    "executionSuccessRate": 0.88,
                    "gasEfficiency": 1.1,
                },
            ]
        },
        engine_state={"summary": {"engines": []}, "items": []},
        telemetry={},
        calibration={
            "items": [
                {"route_family": "funding_arb", "lane": "PROTECTED", "calibration_factor": 0.98}
            ]
        },
        fund_summary={
            "fundStage": "pilot_capital",
            "privateRoutingReady": True,
            "capitalReady": False,
            "internalPrimeReady": True,
            "capitalTruthReasonCodes": ["settled_profit_truth_unavailable"],
            "receiptOutcomeTruthReasonCodes": ["settled_profit_truth_unavailable"],
            "receiptOutcomeTruthRecoveryHistoryStatus": "degraded",
            "receiptOutcomeTruthReliabilityClass": "degraded",
            "receiptOutcomeTruthReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
            "receiptOutcomeTruthReliabilityReasonCodes": [
                "receipt_outcome_truth_reliability_degraded"
            ],
            "recoveryReady": False,
            "recoveryStatus": "capital_truth_restore_required",
            "recoveryReasonCode": "settled_profit_truth_unavailable",
            "recoveryReasonCodes": ["settled_profit_truth_unavailable"],
            "recoveryNextAction": "restore_receipt_outcome_truth",
        },
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert rec["recommended_next_family"] == ""
    assert rec["hold_reason_code"] == "settled_profit_truth_unavailable"
    assert rec["receipt_outcome_truth_reason_codes"] == ["settled_profit_truth_unavailable"]
    assert rec["suggested_next_action"] == "restore_receipt_outcome_truth"
    assert rec["recovery_status"] == "capital_truth_restore_required"
    assert rec["recovery_history_component"] == "receipt_outcome_truth"
    assert rec["blocked_family_details"]["funding_arb"]["receipt_outcome_truth_reason_codes"] == [
        "settled_profit_truth_unavailable"
    ]
    assert (
        rec["blocked_family_details"]["funding_arb"]["recovery_history_component"]
        == "receipt_outcome_truth"
    )
    assert rec["recommended_plan"]["recovery_reason_code"] == "settled_profit_truth_unavailable"
    assert rec["recommended_plan"]["recovery_next_action"] == "restore_receipt_outcome_truth"
