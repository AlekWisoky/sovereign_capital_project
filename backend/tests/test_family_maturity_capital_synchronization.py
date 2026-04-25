from __future__ import annotations

from victor_ai_bot.fund_os.activation_readiness import activation_decision
from victor_ai_bot.fund_os.family_readiness import build_family_readiness
from victor_ai_bot.runtime_services.family_hardening_service import FamilyHardeningService

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
    "fund_summary": {"capitalReady": True, "internalPrimeReady": True, "privateRoutingReady": True},
    "active_families": ["flash_arb"],
    "family_states": {"funding_arb": "observe_only"},
    "exploration_budget": {"used_trades": 0, "max_trades": 3},
}


def test_family_readiness_blocks_family_when_capital_target_is_zero():
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.0}}},
        **BASE_KWARGS,
    )
    assert readiness["ready"] is False
    assert "family_cap_zero" in readiness["blockers"]
    assert readiness["capitalTargetReady"] is False
    assert readiness["familyTargetPct"] == 0.0


def test_family_readiness_resolves_flash_arb_capital_target_alias_to_flashloan_atomic():
    readiness = build_family_readiness(
        family="flash_arb",
        capital_state={"capital_engine": {"family_targets": {"flashloan_atomic": 0.46}}},
        **BASE_KWARGS,
    )
    assert readiness["capitalTargetKnown"] is True
    assert readiness["resolvedFamilyTargetKey"] == "flashloan_atomic"
    assert readiness["capitalTargetReady"] is True
    assert readiness["familyTargetPct"] == 0.46


def test_family_readiness_blocks_family_when_capital_target_is_missing_under_available_treasury_truth():
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"flashloan_atomic": 0.46}}},
        **BASE_KWARGS,
    )
    assert readiness["ready"] is False
    assert readiness["capitalTargetKnown"] is False
    assert readiness["resolvedFamilyTargetKey"] == ""
    assert readiness["capitalTargetReady"] is False
    assert "family_cap_unknown" in readiness["blockers"]
    assert readiness["suggestedNextAction"] == "synchronize_family_capital_targets"


def test_activation_decision_synchronizes_launch_with_family_capital_target_gate():
    decision = activation_decision(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.0}}},
        **BASE_KWARGS,
    )
    assert decision["allowed"] is False
    assert decision["reason_code"] == "family_cap_zero"
    assert "family_cap_zero" in decision["blocked_by"]


def test_activation_decision_blocks_family_when_capital_target_is_missing_under_available_treasury_truth():
    decision = activation_decision(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"flashloan_atomic": 0.46}}},
        **BASE_KWARGS,
    )
    assert decision["allowed"] is False
    assert decision["reason_code"] == "family_cap_unknown"
    assert "family_cap_unknown" in decision["blocked_by"]


class _LaunchProfile:
    active_families = ["flash_arb"]
    family_states = {"flash_arb": "live", "funding_arb": "observe_only"}
    exploration_budget = {"used_trades": 0, "max_trades": 3}


class _LaunchRollout:
    profile = _LaunchProfile()


class _Runtime:
    _cc = None
    _launch_service = None
    _launch_rollout = _LaunchRollout()

    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
            }
        }

    def strategy_scorecards_state(self):
        return BASE_KWARGS["scorecards"]

    def engine_state(self):
        return BASE_KWARGS["engine_state"]

    def telemetry_summary(self):
        return BASE_KWARGS["telemetry"]

    def execution_calibration_state(self):
        return BASE_KWARGS["calibration"]

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"funding_arb": 0.0}}}

    def capital_truth_state(self):
        return {"withdrawal": {"available": False}}


def test_family_hardening_exposes_family_cap_zero_as_no_trade_control():
    payload = FamilyHardeningService().family_state(_Runtime(), "funding_arb")
    assert payload["controls"]["capital_eligible"] is False
    assert payload["controls"]["capital_reason_codes"] == ["family_cap_zero"]
    assert payload["controls"]["treasury_eligible"] is False
    assert payload["controls"]["treasury_reason_codes"] == ["family_cap_zero"]
    assert payload["controls"]["no_trade"] is True
    assert payload["controls"]["no_trade_reason_codes"] == ["family_cap_zero"]
    assert payload["controls"]["family_target_pct"] == 0.0
    assert payload["explanation"]["reason_code"] == "family_cap_zero"


class _CapitalTargetUnknownRuntime(_Runtime):
    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"flashloan_atomic": 0.46}}}


def test_family_hardening_exposes_family_cap_unknown_as_no_trade_control():
    payload = FamilyHardeningService().family_state(_CapitalTargetUnknownRuntime(), "funding_arb")
    assert payload["controls"]["capital_eligible"] is False
    assert payload["controls"]["capital_reason_codes"] == ["family_cap_unknown"]
    assert payload["controls"]["treasury_eligible"] is False
    assert payload["controls"]["treasury_reason_codes"] == ["family_cap_unknown"]
    assert payload["controls"]["no_trade"] is True
    assert payload["controls"]["no_trade_reason_codes"] == ["family_cap_unknown"]
    assert payload["explanation"]["reason_code"] == "family_cap_unknown"


def test_family_readiness_preserves_quarantine_over_weaker_engine_degradation():
    kwargs = dict(BASE_KWARGS)
    kwargs["family_states"] = {"funding_arb": "quarantined"}
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        **kwargs,
    )
    assert readiness["degradedState"] == "quarantined"
    assert readiness["status"] == "quarantined"
    assert "quarantined" in readiness["blockers"]


def test_family_readiness_propagates_capital_truth_reason_codes_into_blockers_and_actions():
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": False,
            "internalPrimeReady": False,
            "privateRoutingReady": True,
            "capitalTruthReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
            "internalPrimeReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert readiness["ready"] is False
    assert readiness["capitalTruthReasonCodes"] == ["internal_prime_journal_borrowed_mismatch"]
    assert readiness["internalPrimeReasonCodes"] == ["internal_prime_journal_borrowed_mismatch"]
    assert "capital_not_ready" in readiness["blockers"]
    assert "internal_prime_not_ready" in readiness["blockers"]
    assert "internal_prime_journal_borrowed_mismatch" in readiness["blockers"]
    assert readiness["suggestedNextAction"] == "repair_internal_prime_accounting"


class _PrimeMismatchRuntime(_Runtime):
    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": False,
                "internalPrimeReady": False,
                "privateRoutingReady": True,
                "capitalTruthReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
                "internalPrimeReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
                "recoveryReady": False,
                "recoveryStatus": "internal_prime_reconciliation_required",
                "recoveryReasonCode": "internal_prime_journal_borrowed_mismatch",
                "recoveryReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
                "recoveryNextAction": "repair_internal_prime_accounting",
            }
        }


def test_family_hardening_surfaces_specific_prime_truth_reason_codes_in_controls():
    payload = FamilyHardeningService().family_state(_PrimeMismatchRuntime(), "funding_arb")
    assert payload["controls"]["capital_eligible"] is False
    assert "internal_prime_journal_borrowed_mismatch" in payload["controls"]["capital_reason_codes"]
    assert payload["controls"]["treasury_eligible"] is False
    assert (
        "internal_prime_journal_borrowed_mismatch" in payload["controls"]["treasury_reason_codes"]
    )
    assert payload["controls"]["recovery_ready"] is False
    assert payload["controls"]["recovery_status"] == "internal_prime_reconciliation_required"
    assert payload["controls"]["recovery_reason_code"] == "internal_prime_journal_borrowed_mismatch"
    assert payload["controls"]["recovery_reason_codes"] == [
        "internal_prime_journal_borrowed_mismatch"
    ]
    assert payload["controls"]["recovery_next_action"] == "repair_internal_prime_accounting"
    assert payload["explanation"]["recovery_status"] == "internal_prime_reconciliation_required"
    assert payload["explanation"]["suggested_next_action"] == "repair_internal_prime_accounting"


def test_activation_decision_prefers_specific_prime_truth_reason_codes():
    decision = activation_decision(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": False,
            "internalPrimeReady": False,
            "privateRoutingReady": True,
            "capitalTruthReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
            "internalPrimeReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert decision["allowed"] is False
    assert decision["reason_code"] == "internal_prime_journal_borrowed_mismatch"
    assert decision["blocked_by"][0] == "internal_prime_journal_borrowed_mismatch"
    assert "capital_not_ready" in decision["blocked_by"]
    assert decision["capital_truth_reason_codes"] == ["internal_prime_journal_borrowed_mismatch"]
    assert decision["internal_prime_reason_codes"] == ["internal_prime_journal_borrowed_mismatch"]


def test_family_readiness_blocks_family_when_global_drawdown_hard_stop_is_active():
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
            "drawdownState": {"hardStop": {"active": True, "reason_codes": ["drawdown_hard_stop"]}},
            "killSwitch": {"suppressions": {}, "history": []},
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert readiness["ready"] is False
    assert readiness["globalExecutionBlocked"] is True
    assert readiness["globalExecutionReasonCodes"] == ["drawdown_hard_stop"]
    assert "drawdown_hard_stop" in readiness["blockers"]
    assert readiness["suggestedNextAction"] == "reduce_drawdown_and_clear_hard_stop"


def test_activation_decision_prefers_global_execution_reason_codes_when_hard_stop_is_active():
    decision = activation_decision(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
            "drawdownState": {"hardStop": {"active": True, "reason_codes": ["drawdown_hard_stop"]}},
            "killSwitch": {"suppressions": {}, "history": []},
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert decision["allowed"] is False
    assert decision["reason_code"] == "drawdown_hard_stop"
    assert decision["global_execution_reason_codes"] == ["drawdown_hard_stop"]
    assert decision["blocked_by"][0] == "drawdown_hard_stop"


class _KillSwitchBlockedRuntime(_Runtime):
    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
                "drawdownState": {"hardStop": {"active": False, "reason_codes": []}},
                "killSwitch": {
                    "suppressions": {
                        "funding_arb|funding_arb|venue": {"reason_codes": ["strategy_failure_mode"]}
                    },
                    "history": [],
                },
            }
        }


def test_family_hardening_surfaces_global_execution_reason_codes_in_controls():
    payload = FamilyHardeningService().family_state(_KillSwitchBlockedRuntime(), "funding_arb")
    assert payload["controls"]["no_trade"] is True
    assert payload["controls"]["global_execution_reason_codes"] == ["strategy_failure_mode"]
    assert "strategy_failure_mode" in payload["controls"]["no_trade_reason_codes"]
    assert (
        payload["explanation"]["suggested_next_action"]
        == "review_kill_switch_and_restore_execution"
    )


def test_family_readiness_blocks_rollout_when_recovery_reliability_is_fragile_after_recent_recovery():
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
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
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert readiness["ready"] is False
    assert readiness["recoveryReliabilityRolloutReady"] is False
    assert "recovery_reliability_fragile" in readiness["blockers"]
    assert "recovery_reliability_fragile" in readiness["reasons"]
    assert readiness["suggestedNextAction"] == "repair_internal_prime_accounting"


def test_activation_decision_blocks_rollout_when_recovery_reliability_is_fragile_after_recent_recovery():
    decision = activation_decision(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
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
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert decision["allowed"] is False
    assert decision["reason_code"] == "recovery_reliability_fragile"
    assert "recovery_reliability_fragile" in decision["blocked_by"]


class _RecoveryFragileRuntime(_Runtime):
    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
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
            }
        }

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"funding_arb": 0.2}}}


def test_family_hardening_surfaces_fragile_recovery_reliability_as_no_trade_control():
    payload = FamilyHardeningService().family_state(_RecoveryFragileRuntime(), "funding_arb")
    assert payload["controls"]["no_trade"] is True
    assert "recovery_reliability_fragile" in payload["controls"]["no_trade_reason_codes"]
    assert payload["controls"]["recovery_reliability_class"] == "fragile"
    assert (
        payload["controls"]["recovery_reliability_next_action"]
        == "repair_internal_prime_accounting"
    )
    assert payload["explanation"]["reason_code"] == "recovery_reliability_fragile"


def test_family_readiness_blocks_rollout_when_family_hardening_service_is_unavailable_even_if_recovery_fields_are_stale_ok():
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
            "familyHardeningStatus": "unavailable",
            "familyHardeningReasonCodes": ["family_hardening_service_unavailable"],
            "recoveryReady": True,
            "recoveryStatus": "ready",
            "recoveryReasonCode": "ok",
            "recoveryReasonCodes": [],
            "recoveryReliabilityClass": "stable",
            "recoveryReliabilityReasonCode": "ok",
            "recoveryReliabilityReasonCodes": [],
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert readiness["ready"] is False
    assert readiness["familyHardeningReady"] is False
    assert readiness["familyHardeningStatus"] == "unavailable"
    assert "family_hardening_service_unavailable" in readiness["blockers"]
    assert readiness["recoveryReady"] is False
    assert readiness["recoveryStatus"] == "family_hardening_restore_required"
    assert readiness["recoveryReasonCode"] == "family_hardening_service_unavailable"
    assert readiness["recoveryHistoryComponent"] == "family_hardening"
    assert readiness["recoveryHistoryStatus"] == "degraded"
    assert readiness["recoveryReliabilityClass"] == "unavailable"
    assert "family_hardening_reliability_unavailable" in readiness["recoveryReliabilityReasonCodes"]
    assert readiness["recoveryReliabilityRolloutReady"] is False
    assert readiness["suggestedNextAction"] == "restore_family_hardening"


def test_activation_decision_blocks_family_when_family_hardening_service_is_unavailable_even_if_recovery_fields_are_stale_ok():
    decision = activation_decision(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
            "familyHardeningStatus": "unavailable",
            "familyHardeningReasonCodes": ["family_hardening_service_unavailable"],
            "recoveryReady": True,
            "recoveryStatus": "ready",
            "recoveryReasonCode": "ok",
            "recoveryReasonCodes": [],
            "recoveryReliabilityClass": "stable",
            "recoveryReliabilityReasonCode": "ok",
            "recoveryReliabilityReasonCodes": [],
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert decision["allowed"] is False
    assert decision["reason_code"] == "family_hardening_service_unavailable"
    assert "family_hardening_service_unavailable" in decision["blocked_by"]
    assert decision["suggested_next_action"] == "restore_family_hardening"


class _FamilyHardeningUnavailableRuntime(_Runtime):
    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
                "familyHardeningStatus": "unavailable",
                "familyHardeningReasonCodes": ["family_hardening_service_unavailable"],
                "recoveryReady": True,
                "recoveryStatus": "ready",
                "recoveryReasonCode": "ok",
                "recoveryReasonCodes": [],
                "recoveryReliabilityClass": "stable",
                "recoveryReliabilityReasonCode": "ok",
                "recoveryReliabilityReasonCodes": [],
            }
        }

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"funding_arb": 0.2}}}


def test_family_hardening_service_surfaces_family_hardening_service_degradation_as_no_trade_control():
    payload = FamilyHardeningService().family_state(
        _FamilyHardeningUnavailableRuntime(), "funding_arb"
    )
    assert payload["controls"]["no_trade"] is True
    assert "family_hardening_service_unavailable" in payload["controls"]["no_trade_reason_codes"]
    assert payload["controls"]["recovery_ready"] is False
    assert payload["controls"]["recovery_status"] == "family_hardening_restore_required"
    assert payload["controls"]["recovery_reason_code"] == "family_hardening_service_unavailable"
    assert payload["controls"]["recovery_history_component"] == "family_hardening"
    assert payload["controls"]["recovery_reliability_class"] == "unavailable"
    assert (
        "family_hardening_reliability_unavailable"
        in payload["controls"]["recovery_reliability_reason_codes"]
    )
    assert payload["controls"]["recovery_reliability_next_action"] == "restore_family_hardening"
    assert payload["explanation"]["reason_code"] == "family_hardening_not_ready"


def test_family_readiness_preserves_family_hardening_recovered_fragility_when_generic_recovery_fields_are_stale_stable():
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": True,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
            "familyHardeningStatus": "ok",
            "familyHardeningReasonCodes": [],
            "familyHardeningRecoveryHistoryStatus": "recovered",
            "familyHardeningRecoveredRecently": True,
            "familyHardeningDegradedCount": 2,
            "familyHardeningRecoveredFragile": True,
            "familyHardeningReliabilityClass": "fragile",
            "familyHardeningReliabilityReasonCode": "family_hardening_reliability_fragile",
            "familyHardeningReliabilityReasonCodes": [
                "family_hardening_reliability_fragile",
                "family_hardening_recovered_fragile",
            ],
            "recoveryReady": True,
            "recoveryStatus": "ready",
            "recoveryReasonCode": "ok",
            "recoveryReasonCodes": [],
            "recoveryReliabilityClass": "stable",
            "recoveryReliabilityReasonCode": "ok",
            "recoveryReliabilityReasonCodes": [],
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert readiness["recoveryHistoryComponent"] == "family_hardening"
    assert readiness["recoveryHistoryStatus"] == "recovered"
    assert readiness["familyHardeningRecoveryHistoryStatus"] == "recovered"
    assert readiness["familyHardeningDegradedCount"] == 2
    assert readiness["familyHardeningRecoveredRecently"] is True
    assert readiness["familyHardeningRecoveredFragile"] is True
    assert readiness["recoveryReliabilityClass"] == "fragile"
    assert readiness["recoveryReliabilityReasonCode"] == "family_hardening_reliability_fragile"
    assert "family_hardening_recovered_fragile" in readiness["recoveryReliabilityReasonCodes"]
    assert readiness["recoveryReliabilityRolloutReady"] is False
    assert "recovery_reliability_fragile" in readiness["blockers"]


class _FamilyHardeningRecoveredFragileRuntime(_Runtime):
    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
                "familyHardeningStatus": "ok",
                "familyHardeningReasonCodes": [],
                "familyHardeningRecoveryHistoryStatus": "recovered",
                "familyHardeningRecoveredRecently": True,
                "familyHardeningDegradedCount": 2,
                "familyHardeningRecoveredFragile": True,
                "familyHardeningReliabilityClass": "fragile",
                "familyHardeningReliabilityReasonCode": "family_hardening_reliability_fragile",
                "familyHardeningReliabilityReasonCodes": [
                    "family_hardening_reliability_fragile",
                    "family_hardening_recovered_fragile",
                ],
                "recoveryReady": True,
                "recoveryStatus": "ready",
                "recoveryReasonCode": "ok",
                "recoveryReasonCodes": [],
                "recoveryReliabilityClass": "stable",
                "recoveryReliabilityReasonCode": "ok",
                "recoveryReliabilityReasonCodes": [],
            }
        }

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"funding_arb": 0.2}}}


def test_family_hardening_service_preserves_family_hardening_recovered_fragility_from_readiness_history():
    payload = FamilyHardeningService().family_state(
        _FamilyHardeningRecoveredFragileRuntime(), "funding_arb"
    )
    assert payload["readiness"]["recoveryHistoryComponent"] == "family_hardening"
    assert payload["readiness"]["recoveryHistoryStatus"] == "recovered"
    assert payload["readiness"]["familyHardeningRecoveryHistoryStatus"] == "recovered"
    assert payload["controls"]["recovery_reliability_class"] == "fragile"
    assert (
        payload["controls"]["recovery_reliability_reason_code"]
        == "family_hardening_reliability_fragile"
    )
    assert (
        "family_hardening_recovered_fragile"
        in payload["controls"]["recovery_reliability_reason_codes"]
    )
    assert payload["controls"]["no_trade"] is True
    assert "recovery_reliability_fragile" in payload["controls"]["no_trade_reason_codes"]


def test_family_hardening_summary_surfaces_top_level_family_hardening_service_degradation():
    payload = FamilyHardeningService().summary(_FamilyHardeningUnavailableRuntime())

    assert payload["ok"] is False
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "family_hardening_service_unavailable"
    assert payload["reason_codes"] == ["family_hardening_service_unavailable"]
    assert payload["recovery_ready"] is False
    assert payload["recovery_status"] == "family_hardening_restore_required"
    assert payload["recovery_reason_code"] == "family_hardening_service_unavailable"
    assert payload["recovery_history_component"] == "family_hardening"
    assert payload["recovery_history_status"] == "degraded"
    assert payload["recovery_reliability_class"] == "unavailable"
    assert payload["recovery_reliability_reason_code"] == "family_hardening_reliability_unavailable"
    assert (
        "family_hardening_reliability_unavailable" in payload["recovery_reliability_reason_codes"]
    )
    assert payload["family_hardening_reason_codes"] == ["family_hardening_service_unavailable"]
    assert payload["blocked_non_core_family_count"] >= 1
    assert payload["items"]


def test_family_hardening_summary_surfaces_top_level_recovered_fragility_history():
    payload = FamilyHardeningService().summary(_FamilyHardeningRecoveredFragileRuntime())

    assert payload["ok"] is True
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "family_hardening_reliability_fragile"
    assert "family_hardening_reliability_fragile" in payload["reason_codes"]
    assert payload["recovery_ready"] is False
    assert payload["recovery_status"] == "degraded"
    assert payload["recovery_reason_code"] == "family_hardening_reliability_fragile"
    assert payload["recovery_next_action"] == "stabilize_recovery_before_rollout"
    assert payload["recovery_history_component"] == "family_hardening"
    assert payload["recovery_history_status"] == "recovered"
    assert payload["recovery_degraded_count"] == 2
    assert payload["recovery_recovered_recently"] is True
    assert payload["recovery_degradation_severity_class"] == "recovering"
    assert payload["recovery_reliability_class"] == "fragile"
    assert payload["recovery_reliability_reason_code"] == "family_hardening_reliability_fragile"
    assert "family_hardening_recovered_fragile" in payload["recovery_reliability_reason_codes"]
    assert payload["recovery_recovered_fragile"] is True
    assert payload["family_hardening_recovery_history_status"] == "recovered"
    assert payload["family_hardening_degraded_count"] == 2
    assert payload["family_hardening_recovered_recently"] is True
    assert payload["family_hardening_recovered_fragile"] is True


def test_family_readiness_preserves_receipt_outcome_truth_as_first_class_recovery_component():
    readiness = build_family_readiness(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": False,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
            "capitalTruthReasonCodes": ["settled_profit_truth_unavailable"],
            "receiptOutcomeTruthReasonCodes": ["settled_profit_truth_unavailable"],
            "receiptOutcomeTruthRecoveryHistoryStatus": "degraded",
            "receiptOutcomeTruthReliabilityClass": "degraded",
            "receiptOutcomeTruthReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
            "receiptOutcomeTruthReliabilityReasonCodes": [
                "receipt_outcome_truth_reliability_degraded"
            ],
            "recoveryReady": True,
            "recoveryStatus": "ready",
            "recoveryReasonCode": "ok",
            "recoveryReasonCodes": [],
            "recoveryReliabilityClass": "stable",
            "recoveryReliabilityReasonCode": "ok",
            "recoveryReliabilityReasonCodes": [],
        },
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert readiness["ready"] is False
    assert readiness["receiptOutcomeTruthReasonCodes"] == ["settled_profit_truth_unavailable"]
    assert readiness["suggestedNextAction"] == "restore_receipt_outcome_truth"
    assert readiness["recoveryStatus"] == "capital_truth_restore_required"
    assert readiness["recoveryReasonCode"] == "settled_profit_truth_unavailable"
    assert readiness["recoveryHistoryComponent"] == "receipt_outcome_truth"
    assert readiness["receiptOutcomeTruthRecoveryHistoryStatus"] == "degraded"
    assert readiness["recoveryReliabilityClass"] == "degraded"
    assert (
        readiness["recoveryReliabilityReasonCode"] == "receipt_outcome_truth_reliability_degraded"
    )


def test_activation_decision_preserves_receipt_outcome_truth_reason_family():
    decision = activation_decision(
        family="funding_arb",
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
        fund_summary={
            "capitalReady": False,
            "internalPrimeReady": True,
            "privateRoutingReady": True,
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
        **{k: v for k, v in BASE_KWARGS.items() if k != "fund_summary"},
    )
    assert decision["allowed"] is False
    assert decision["reason_code"] == "settled_profit_truth_unavailable"
    assert decision["receipt_outcome_truth_reason_codes"] == ["settled_profit_truth_unavailable"]
    assert decision["suggested_next_action"] == "restore_receipt_outcome_truth"
