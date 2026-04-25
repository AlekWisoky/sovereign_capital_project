from __future__ import annotations

from dataclasses import dataclass
import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from victor_ai_bot.execution import ExecResult
from victor_ai_bot.caq_kds.bus import BUS
from victor_ai_bot.execution_capture.route_execution_plan import apply_execution_route_plan
from victor_ai_bot.outcomes import ExecutionOutcome
from victor_ai_bot.degraded_state_contract import attach_state_contract, contract_from_surface
from victor_ai_bot.profitability_state import (
    build_terminal_profitability_authority,
    has_profitability_contract,
    profitability_state_view,
    refresh_post_mutation_revalidation_contract,
    set_profitability_state,
)

from .runtime_context import build_execution_runtime_signals
from .profitability_truth import inspect_profit_after_costs_truth
from .family_hardening_service import family_hardening_unavailable_summary
from .capital_truth_health_contract import runtime_capital_truth_health
from .route_runtime_truth import execution_route_runtime_reason_codes, execution_route_truth
from .treasury_governance_truth import treasury_governance_view
from ..fund_os.family_identity import family_identity, is_core_launch_family

_SAFE_RUNTIME_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


_EXECUTION_PLAN_FAILURES = _SAFE_RUNTIME_EXCEPTIONS + (IndexError,)
_RECORDING_FAILURES = _SAFE_RUNTIME_EXCEPTIONS + (IndexError,)
_PENDING_QUEUE_FAILURES = _SAFE_RUNTIME_EXCEPTIONS + (asyncio.QueueFull,)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return int(default)


def _sync_scaled_profit_fields(opp: Any, scale_mult: float) -> None:
    try:
        opp.expected_profit_raw = str(max(0, int(int(opp.expected_profit_raw) * scale_mult)))
    except (AttributeError, KeyError, TypeError, ValueError):
        pass

    meta = getattr(opp, "meta", None)
    if not isinstance(meta, dict):
        return

    brain = meta.setdefault("brain", {}) if isinstance(meta, dict) else {}
    safety = meta.get("safety")
    if not isinstance(safety, dict):
        safety = {}
        meta["safety"] = safety

    profit_after_present = "profit_after_costs" in meta
    safety_profit_present = "profit_after_costs_wei" in safety
    if not profit_after_present and not safety_profit_present:
        return

    raw_after = (
        meta.get("profit_after_costs")
        if profit_after_present
        else safety.get("profit_after_costs_wei")
    )
    try:
        profit_after = max(0, int(str(raw_after)))
    except (TypeError, ValueError):
        meta["profit_after_costs"] = "0"
        safety["profit_after_costs_wei"] = "0"
        brain["profit_after_costs_sync"] = "invalid_input_zeroed"
        return

    scaled_after = max(0, int(profit_after * scale_mult))
    meta["profit_after_costs"] = str(scaled_after)
    safety["profit_after_costs_wei"] = str(scaled_after)

    if "profit_after_costs_usd_micro" in safety:
        try:
            usd_after = max(0, int(str(safety.get("profit_after_costs_usd_micro") or "0")))
            safety["profit_after_costs_usd_micro"] = str(max(0, int(usd_after * scale_mult)))
        except (TypeError, ValueError):
            safety["profit_after_costs_usd_micro"] = "0"
            brain["profit_after_costs_usd_sync"] = "invalid_input_zeroed"

    brain["profit_after_costs_sync"] = "scaled"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _unique_strings(values: List[Any]) -> List[str]:
    out: List[str] = []
    for value in values:
        sval = str(value or "")
        if sval and sval not in out:
            out.append(sval)
    return out


def _profit_after_costs_gate_info(opp: Any) -> Tuple[int, bool, str, Dict[str, Any]]:
    truth = inspect_profit_after_costs_truth(getattr(opp, "meta", None))
    return (
        int(max(0, truth.value_wei)),
        bool(truth.verified and truth.positive),
        str(truth.reason_code),
        {
            "profitAfterCostsCanonical": bool(truth.verified),
            "profitAfterCostsPositive": bool(truth.positive),
            "profitAfterCostsMetaPresent": bool(truth.meta_present),
            "profitAfterCostsSafetyPresent": bool(truth.safety_present),
            "profitAfterCostsMetaWei": (
                str(truth.meta_value_wei) if truth.meta_value_wei is not None else ""
            ),
            "profitAfterCostsSafetyWei": (
                str(truth.safety_value_wei) if truth.safety_value_wei is not None else ""
            ),
        },
    )


def _canonical_family_identity(value: Any) -> Dict[str, Any]:
    family = str(value or "flashloan_atomic") or "flashloan_atomic"
    return family_identity(family)


def _opportunity_family_identity(opp: Any) -> Dict[str, Any]:
    meta = _safe_dict(getattr(opp, "meta", None))
    return _canonical_family_identity(
        meta.get("strategy_family") or meta.get("route_family") or "flashloan_atomic"
    )


def _opportunity_family(opp: Any) -> str:
    return str(_opportunity_family_identity(opp).get("launchFamily") or "")


def _decision_metadata(decision: Any | None) -> Dict[str, Any]:
    if decision is None or not isinstance(getattr(decision, "metadata", None), dict):
        return {}
    return dict(getattr(decision, "metadata", {}) or {})


def _family_hardening_gate_unavailable_metadata(family: str, *, detail: str = "") -> Dict[str, Any]:
    summary = family_hardening_unavailable_summary(family)
    reason_code = "family_hardening_unavailable"
    metadata: Dict[str, Any] = {
        "blocked": True,
        "family": str(family),
        "reason_code": reason_code,
        "reason_codes": [reason_code],
        "suggested_next_action": str(
            summary.get("recovery_next_action") or "restore_family_hardening"
        ),
        "recovery_ready": bool(summary.get("recovery_ready", False)),
        "recovery_status": str(
            summary.get("recovery_status") or "family_hardening_restore_required"
        ),
        "recovery_reason_code": str(
            summary.get("recovery_reason_code")
            or summary.get("reason_code")
            or "family_hardening_service_unavailable"
        ),
        "recovery_reason_codes": _unique_strings(
            list(summary.get("recovery_reason_codes") or [])
            or [summary.get("recovery_reason_code") or summary.get("reason_code") or ""]
        ),
        "recovery_next_action": str(
            summary.get("recovery_next_action") or "restore_family_hardening"
        ),
        "recovery_history_component": str(
            summary.get("recovery_history_component") or "family_hardening"
        ),
        "recovery_history_status": str(summary.get("recovery_history_status") or "degraded"),
        "recovery_reliability_class": str(
            summary.get("recovery_reliability_class") or "unavailable"
        ),
        "recovery_reliability_reason_code": str(
            summary.get("recovery_reliability_reason_code")
            or "family_hardening_reliability_unavailable"
        ),
        "recovery_reliability_reason_codes": _unique_strings(
            list(summary.get("recovery_reliability_reason_codes") or [])
            or [
                summary.get("recovery_reliability_reason_code")
                or "family_hardening_reliability_unavailable"
            ]
        ),
        "recovery_reliability_next_action": str(
            summary.get("recovery_reliability_next_action")
            or summary.get("recovery_next_action")
            or "restore_family_hardening"
        ),
        "family_hardening_reason_codes": _unique_strings(
            list(summary.get("family_hardening_reason_codes") or [])
            or [summary.get("reason_code") or ""]
        ),
        "family_hardening_recovery_history_status": str(
            summary.get("family_hardening_recovery_history_status") or "degraded"
        ),
        "family_hardening_reliability_class": str(
            summary.get("family_hardening_reliability_class") or "unavailable"
        ),
        "family_hardening_reliability_reason_code": str(
            summary.get("family_hardening_reliability_reason_code")
            or "family_hardening_reliability_unavailable"
        ),
        "family_hardening_reliability_reason_codes": _unique_strings(
            list(summary.get("family_hardening_reliability_reason_codes") or [])
            or [
                summary.get("family_hardening_reliability_reason_code")
                or "family_hardening_reliability_unavailable"
            ]
        ),
    }
    if detail:
        metadata["detail"] = str(detail)
    return metadata


def _opportunity_meta_capture_payload(opp: Any) -> Dict[str, Any]:
    meta = _safe_dict(getattr(opp, "meta", None))
    return _safe_dict(meta.get("capture"))


def _opportunity_meta_capture_metadata(opp: Any) -> Dict[str, Any]:
    capture = _opportunity_meta_capture_payload(opp)
    return _safe_dict(capture.get("metadata"))


def _normalize_send_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"private", "protected_rpc"}:
        return "private"
    if mode == "public":
        return "public"
    return mode


def _capture_lane(value: Any) -> str:
    lane = str(value or "").strip().lower()
    if lane in {"private", "protected", "protected_rpc"}:
        return "private"
    if lane == "public":
        return "public"
    return lane


def _capture_coordination_metadata(runtime: Any | None, opp: Any) -> Dict[str, Any]:
    capture = _opportunity_meta_capture_payload(opp)
    capture_meta = _opportunity_meta_capture_metadata(opp)
    endpoint = _safe_dict(capture_meta.get("endpoint_selection"))
    adversarial = _safe_dict(capture_meta.get("adversarial_state"))
    raw_meta = _safe_dict(getattr(opp, "meta", None))
    route_runtime = _safe_dict(raw_meta.get("execution_route_runtime"))
    route_runtime_reason_codes = execution_route_runtime_reason_codes(route_runtime)
    cfg = getattr(runtime, "cfg", None) if runtime is not None else None
    execution_cfg = getattr(cfg, "execution", None) if cfg is not None else None
    controls = (
        getattr(getattr(runtime, "_cc", None), "controls", None) if runtime is not None else None
    )
    operator_force_send_mode = _normalize_send_mode(
        getattr(controls, "force_send_mode", "") if controls is not None else ""
    )
    configured_send_mode = _normalize_send_mode(
        getattr(execution_cfg, "send_mode", "") if execution_cfg is not None else ""
    )
    effective_send_mode = operator_force_send_mode or configured_send_mode
    lane = _capture_lane(capture.get("lane") or capture_meta.get("lane") or endpoint.get("lane"))
    return {
        "capturePresent": bool(capture),
        "captureAction": str(capture.get("action") or "").strip().lower(),
        "captureReason": str(capture.get("reason") or ""),
        "captureDropReason": str(capture.get("drop_reason") or capture.get("reason") or ""),
        "captureLane": lane,
        "captureSendMode": _normalize_send_mode(capture.get("send_mode") or ""),
        "effectiveSendMode": effective_send_mode,
        "operatorForceSendMode": operator_force_send_mode,
        "requiresPrivateLane": lane == "private",
        "endpointHint": str(capture.get("endpoint_hint") or endpoint.get("endpoint") or ""),
        "relayHint": str(capture.get("relay_hint") or endpoint.get("relay") or ""),
        "endpointReason": str(endpoint.get("reason") or endpoint.get("pressure_class") or ""),
        "adversarialState": adversarial,
        "captureRouteRuntime": route_runtime,
        "captureRouteRuntimeReasonCodes": route_runtime_reason_codes,
    }


def _capture_coordination_failure(runtime: Any | None, opp: Any) -> Dict[str, Any]:
    metadata = _capture_coordination_metadata(runtime, opp)
    action = str(metadata.get("captureAction") or "")
    drop_reason = str(metadata.get("captureDropReason") or "")
    if action == "drop":
        reason = drop_reason or "execution_capture_drop"
        return {
            "reason": reason,
            "reason_codes": [reason],
            "suggested_next_action": "refresh_execution_capture",
            "metadata": metadata,
        }
    if (
        bool(metadata.get("requiresPrivateLane", False))
        and str(metadata.get("effectiveSendMode") or "") == "public"
    ):
        reason_codes = ["private_lane_required"]
        if str(metadata.get("operatorForceSendMode") or "") == "public":
            reason_codes.append("operator_force_send_mode_conflict")
            next_action = "clear_force_send_mode_or_restore_private_submission"
        else:
            next_action = "restore_private_submission"
        return {
            "reason": "private_lane_required",
            "reason_codes": reason_codes,
            "suggested_next_action": next_action,
            "metadata": metadata,
        }
    adversarial = _safe_dict(metadata.get("adversarialState"))
    if "post_ordering_realized_edge" in adversarial:
        try:
            post_ordering_realized_edge = float(
                adversarial.get("post_ordering_realized_edge") or 0.0
            )
        except (TypeError, ValueError):
            post_ordering_realized_edge = 0.0
        if post_ordering_realized_edge <= 0.0:
            reason = "post_ordering_realized_edge_non_positive"
            return {
                "reason": reason,
                "reason_codes": [reason],
                "suggested_next_action": "refresh_execution_capture",
                "metadata": metadata,
            }
    return {}


def _flashloan_metadata(opp: Any, decision: Any | None) -> Dict[str, Any]:
    decision_meta = _decision_metadata(decision)
    if isinstance(decision_meta.get("flashloan_resilience"), dict):
        return dict(decision_meta.get("flashloan_resilience") or {})
    capture_meta = _opportunity_meta_capture_metadata(opp)
    if isinstance(capture_meta.get("flashloan_resilience"), dict):
        return dict(capture_meta.get("flashloan_resilience") or {})
    return {}


def _is_flashloan_family(opp: Any, decision: Any | None) -> bool:
    family = _opportunity_family(opp)
    if is_core_launch_family(family):
        return True
    decision_meta = _decision_metadata(decision)
    route_family = str(decision_meta.get("route_family") or "")
    if "flash" in route_family:
        return True
    capture_meta = _opportunity_meta_capture_metadata(opp)
    route_family = str(capture_meta.get("route_family") or "")
    if "flash" in route_family:
        return True
    raw_meta = _safe_dict(getattr(opp, "meta", None))
    return "flash" in str(raw_meta.get("strategy_family") or raw_meta.get("route_family") or "")


def _level_rank(level: Any) -> int:
    order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "MAXIMUM": 3}
    return int(order.get(str(level or "LOW").upper(), 0))


@dataclass(frozen=True)
class ExecutionGateResult:
    allowed: bool
    reason: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class OperatorOverrideResult:
    opportunity: Any
    force_dry_run: bool
    old_gas_mode: str
    old_send_mode: str


@dataclass(frozen=True)
class ExecutionPreparationResult:
    opportunity: Any
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class AutoExecutionPreflightResult:
    proceed: bool
    opportunity: Any
    decision: Any | None
    force_dry_run: bool
    old_gas_mode: str
    old_send_mode: str
    send_url: str
    read_url: str
    blocked_result: ExecResult | None = None
    metadata: Dict[str, Any] | None = None


@dataclass(frozen=True)
class AutoTradeAdmissionResult:
    allowed: bool
    stage: str
    reason: str
    opportunity: Any
    gate: Dict[str, Any]
    plan: Dict[str, Any]


@dataclass(frozen=True)
class AutoTradeAdmissionHandlingResult:
    opportunity: Any
    blocked_result: ExecResult | None


@dataclass(frozen=True)
class SuperstructurePreExecuteResult:
    opportunity: Any
    blocked_result: ExecResult | None
    super_enabled: bool
    old_gas_mode: str
    old_send_mode: str


@dataclass(frozen=True)
class GovernancePreExecuteResult:
    opportunity: Any
    blocked_result: ExecResult | None


def _normalize_admission_gate_metadata(
    metadata: Dict[str, Any] | None, *, reason: str
) -> Dict[str, Any]:
    out = dict(metadata or {})
    reason_code = str(out.get("reason_code") or out.get("holdReasonCode") or reason or "")
    reason_codes = [
        str(x) for x in list(out.get("reason_codes") or out.get("holdReasonCodes") or []) if str(x)
    ]
    if reason_code and reason_code not in reason_codes and reason_code != "ok":
        reason_codes = [reason_code, *reason_codes]
    suggested_next_action = str(
        out.get("suggested_next_action")
        or out.get("suggestedNextAction")
        or out.get("recoveryNextAction")
        or ""
    )
    if reason_code:
        out["reason_code"] = reason_code
    out["reason_codes"] = reason_codes
    out["suggested_next_action"] = suggested_next_action
    return out


def _observe_auto_trade_recovery(runtime: Any, admission: AutoTradeAdmissionResult) -> None:
    try:
        from .state_service import observed_auto_trade_recovery_info

        observed_auto_trade_recovery_info(runtime, admission)
    except _SAFE_RUNTIME_EXCEPTIONS:
        pass


def _admission_failure_result(
    opp: Any, *, force_dry_run: bool, detail: str
) -> Tuple[AutoTradeAdmissionHandlingResult, AutoTradeAdmissionResult]:
    plan = {
        "admission": {
            "blocked": True,
            "reason_code": "admission_gate_failed",
            "reason_codes": ["admission_gate_failed"],
            "suggested_next_action": "restore_auto_trade_admission_state",
            "detail": str(detail),
        }
    }
    admission = AutoTradeAdmissionResult(
        False,
        "admission_hold",
        "admission_gate_failed",
        opp,
        dict(plan.get("admission") or {}),
        dict(plan),
    )
    return (
        AutoTradeAdmissionHandlingResult(
            opportunity=opp,
            blocked_result=ExecResult(
                False,
                bool(force_dry_run),
                "admission_hold:admission_gate_failed",
                attempted=False,
                plan=plan,
            ),
        ),
        admission,
    )


def _apply_superstructure_planner_overrides(runtime: Any, overrides: Dict[str, Any] | None) -> None:
    ov = dict(overrides or {})
    try:
        gm = str(ov.get("gas_mode") or "")
        if gm in {"standard", "fast", "instant"}:
            runtime.cfg.execution.gas_mode = gm
            runtime.metrics.gas_mode = gm
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    try:
        smode = str(ov.get("send_mode") or "")
        if smode in {"public", "private", "protected_rpc"}:
            runtime.cfg.execution.send_mode = smode
            runtime.metrics.send_mode = smode
    except (AttributeError, KeyError, TypeError, ValueError):
        pass


class ExecutionService:
    def gate(
        self, *, capture_action: str, telemetry_ok: bool = True, capital_ok: bool = True
    ) -> ExecutionGateResult:
        if capture_action == "drop":
            return ExecutionGateResult(False, "capture_drop", {})
        if not telemetry_ok:
            return ExecutionGateResult(False, "telemetry_degraded", {"degraded": True})
        if not capital_ok:
            return ExecutionGateResult(False, "capital_denied", {"degraded": True})
        return ExecutionGateResult(True, "ok", {})

    def auto_trade_hold_gate(self, runtime: Any) -> ExecutionGateResult:
        """Fail closed for auto-trading when canonical fund hold truth is degraded.

        This keeps live execution aligned with the same global/capital/internal-prime
        blockers already exposed to fund, launch, and operator surfaces.
        """

        try:
            if not hasattr(runtime, "fund_summary_state"):
                return ExecutionGateResult(
                    False,
                    "fund_summary_unavailable",
                    {
                        "blocked": True,
                        "holdReasonCode": "fund_summary_unavailable",
                        "holdReasonCodes": ["fund_summary_unavailable"],
                        "suggestedNextAction": "restore_fund_summary",
                        "recoveryReady": False,
                        "recoveryStatus": "fund_summary_restore_required",
                        "recoveryReasonCode": "fund_summary_unavailable",
                        "recoveryReasonCodes": ["fund_summary_unavailable"],
                        "recoveryNextAction": "restore_fund_summary",
                    },
                )
            summary = runtime.fund_summary_state()
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            return ExecutionGateResult(
                False,
                "fund_summary_unavailable",
                {
                    "blocked": True,
                    "holdReasonCode": "fund_summary_unavailable",
                    "holdReasonCodes": ["fund_summary_unavailable"],
                    "suggestedNextAction": "restore_fund_summary",
                    "recoveryReady": False,
                    "recoveryStatus": "fund_summary_restore_required",
                    "recoveryReasonCode": "fund_summary_unavailable",
                    "recoveryReasonCodes": ["fund_summary_unavailable"],
                    "recoveryNextAction": "restore_fund_summary",
                    "detail": str(exc),
                },
            )

        health = _safe_dict(_safe_dict(summary).get("health") or summary)
        capital_truth_health = runtime_capital_truth_health(
            runtime, fund_summary=_safe_dict(summary)
        )
        global_execution_reason_codes = _unique_strings(
            list(health.get("globalExecutionReasonCodes") or [])
        )
        capital_truth_reason_codes = _unique_strings(
            list(health.get("capitalTruthReasonCodes") or [])
        )
        capital_truth_freshness_reason_codes = _unique_strings(
            list(health.get("capitalTruthFreshnessReasonCodes") or [])
        )
        capital_truth_reason_code = str(health.get("capitalTruthReasonCode") or "")
        capital_truth_freshness_reason_code = str(
            health.get("capitalTruthFreshnessReasonCode") or ""
        )
        helper_capital_truth_reason_codes = _unique_strings(
            list(capital_truth_health.get("reasonCodes") or [])
        )
        helper_capital_truth_freshness_reason_codes = _unique_strings(
            list(capital_truth_health.get("freshnessReasonCodes") or [])
        )
        helper_capital_truth_reason_code = str(capital_truth_health.get("reasonCode") or "")
        helper_capital_truth_freshness_reason_code = str(
            capital_truth_health.get("freshnessReasonCode") or ""
        )
        if not capital_truth_reason_codes:
            capital_truth_reason_codes = helper_capital_truth_reason_codes
        if not capital_truth_freshness_reason_codes:
            capital_truth_freshness_reason_codes = helper_capital_truth_freshness_reason_codes
        if not capital_truth_reason_code or capital_truth_reason_code == "ok":
            capital_truth_reason_code = helper_capital_truth_reason_code
        if not capital_truth_freshness_reason_code or capital_truth_freshness_reason_code == "ok":
            capital_truth_freshness_reason_code = helper_capital_truth_freshness_reason_code
        receipt_outcome_truth_reason_codes = _unique_strings(
            list(health.get("receiptOutcomeTruthReasonCodes") or [])
        )
        internal_prime_reason_codes = _unique_strings(
            list(health.get("internalPrimeReasonCodes") or [])
        )
        family_hardening_reason_codes = _unique_strings(
            list(health.get("familyHardeningReasonCodes") or [])
        )
        family_hardening_reliability_reason_codes = _unique_strings(
            list(health.get("familyHardeningReliabilityReasonCodes") or [])
        )
        family_hardening_reliability_reason_code = str(
            health.get("familyHardeningReliabilityReasonCode")
            or (
                family_hardening_reliability_reason_codes[0]
                if family_hardening_reliability_reason_codes
                else (
                    "family_hardening_reliability_unavailable"
                    if family_hardening_reason_codes
                    else "ok"
                )
            )
        )
        if (
            family_hardening_reliability_reason_code != "ok"
            and family_hardening_reliability_reason_code
            not in family_hardening_reliability_reason_codes
        ):
            family_hardening_reliability_reason_codes = [
                family_hardening_reliability_reason_code,
                *family_hardening_reliability_reason_codes,
            ]
        family_hardening_reliability_class = str(
            health.get("familyHardeningReliabilityClass")
            or ("unavailable" if family_hardening_reason_codes else "stable")
        )
        if family_hardening_reason_codes and family_hardening_reliability_class == "stable":
            family_hardening_reliability_class = "unavailable"
        family_hardening_recovery_history_status = str(
            health.get("familyHardeningRecoveryHistoryStatus")
            or ("degraded" if family_hardening_reason_codes else "steady")
        )
        hold_reason_codes = _unique_strings(
            list(health.get("holdReasonCodes") or [])
            + global_execution_reason_codes
            + family_hardening_reason_codes
            + receipt_outcome_truth_reason_codes
            + capital_truth_reason_codes
            + internal_prime_reason_codes
        )
        if (
            capital_truth_health.get("blocked", False)
            and not list(health.get("holdReasonCodes") or [])
            and not capital_truth_reason_codes
        ):
            capital_truth_reason_codes = helper_capital_truth_reason_codes
            if not capital_truth_freshness_reason_codes:
                capital_truth_freshness_reason_codes = helper_capital_truth_freshness_reason_codes
            if not hold_reason_codes:
                hold_reason_codes = _unique_strings(
                    helper_capital_truth_reason_codes or helper_capital_truth_freshness_reason_codes
                )
        hold_reason_code = str(
            health.get("holdReasonCode") or (hold_reason_codes[0] if hold_reason_codes else "")
        )
        if hold_reason_code and hold_reason_code not in hold_reason_codes:
            hold_reason_codes = [hold_reason_code, *hold_reason_codes]
        recovery_reason_codes = _unique_strings(list(health.get("recoveryReasonCodes") or []))
        if not recovery_reason_codes:
            if global_execution_reason_codes:
                recovery_reason_codes = list(global_execution_reason_codes)
            elif family_hardening_reason_codes:
                recovery_reason_codes = list(family_hardening_reason_codes)
            elif internal_prime_reason_codes:
                recovery_reason_codes = list(internal_prime_reason_codes)
            elif receipt_outcome_truth_reason_codes:
                recovery_reason_codes = list(receipt_outcome_truth_reason_codes)
            elif capital_truth_reason_codes:
                recovery_reason_codes = list(capital_truth_reason_codes)
        recovery_reason_code = str(
            health.get("recoveryReasonCode")
            or (recovery_reason_codes[0] if recovery_reason_codes else (hold_reason_code or "ok"))
        )
        recovery_history_component = str(
            health.get("recoveryHistoryComponent")
            or (
                "family_hardening"
                if family_hardening_reason_codes
                else ("receipt_outcome_truth" if receipt_outcome_truth_reason_codes else "")
            )
        )
        recovery_history_status = str(
            health.get("recoveryHistoryStatus")
            or (
                family_hardening_recovery_history_status
                if family_hardening_reason_codes
                else "steady"
            )
        )
        recovery_reliability_reason_codes = _unique_strings(
            list(health.get("recoveryReliabilityReasonCodes") or [])
        )
        receipt_outcome_truth_reliability_reason_codes = _unique_strings(
            list(health.get("receiptOutcomeTruthReliabilityReasonCodes") or [])
        )
        receipt_outcome_truth_reliability_reason_code = str(
            health.get("receiptOutcomeTruthReliabilityReasonCode")
            or (
                receipt_outcome_truth_reliability_reason_codes[0]
                if receipt_outcome_truth_reliability_reason_codes
                else (
                    "receipt_outcome_truth_reliability_degraded"
                    if receipt_outcome_truth_reason_codes
                    else "ok"
                )
            )
        )
        if (
            receipt_outcome_truth_reliability_reason_code != "ok"
            and receipt_outcome_truth_reliability_reason_code
            not in receipt_outcome_truth_reliability_reason_codes
        ):
            receipt_outcome_truth_reliability_reason_codes = [
                receipt_outcome_truth_reliability_reason_code,
                *receipt_outcome_truth_reliability_reason_codes,
            ]
        receipt_outcome_truth_reliability_class = str(
            health.get("receiptOutcomeTruthReliabilityClass")
            or ("degraded" if receipt_outcome_truth_reason_codes else "stable")
        )
        if (
            receipt_outcome_truth_reason_codes
            and receipt_outcome_truth_reliability_class == "stable"
        ):
            receipt_outcome_truth_reliability_class = "degraded"
        if not recovery_reliability_reason_codes:
            if family_hardening_reason_codes:
                recovery_reliability_reason_codes = list(family_hardening_reliability_reason_codes)
            elif receipt_outcome_truth_reason_codes:
                recovery_reliability_reason_codes = list(
                    receipt_outcome_truth_reliability_reason_codes
                )
        recovery_reliability_reason_code = str(
            health.get("recoveryReliabilityReasonCode")
            or (
                recovery_reliability_reason_codes[0]
                if recovery_reliability_reason_codes
                else (
                    family_hardening_reliability_reason_code
                    if family_hardening_reason_codes
                    else "ok"
                )
            )
        )
        if (
            recovery_reliability_reason_code != "ok"
            and recovery_reliability_reason_code not in recovery_reliability_reason_codes
        ):
            recovery_reliability_reason_codes = [
                recovery_reliability_reason_code,
                *recovery_reliability_reason_codes,
            ]
        recovery_reliability_class = str(
            health.get("recoveryReliabilityClass")
            or (
                family_hardening_reliability_class
                if family_hardening_reason_codes
                else (
                    receipt_outcome_truth_reliability_class
                    if receipt_outcome_truth_reason_codes
                    else "stable"
                )
            )
        )
        if family_hardening_reason_codes and recovery_reliability_class == "stable":
            recovery_reliability_class = family_hardening_reliability_class
        elif receipt_outcome_truth_reason_codes and recovery_reliability_class == "stable":
            recovery_reliability_class = receipt_outcome_truth_reliability_class
        if recovery_reason_code == "ok" and recovery_reason_codes:
            recovery_reason_code = recovery_reason_codes[0]
        elif recovery_reason_code != "ok" and recovery_reason_code not in recovery_reason_codes:
            recovery_reason_codes = [recovery_reason_code, *recovery_reason_codes]
        recovery_ready = bool(
            health.get(
                "recoveryReady",
                not bool(
                    global_execution_reason_codes
                    or family_hardening_reason_codes
                    or receipt_outcome_truth_reason_codes
                    or capital_truth_reason_codes
                    or internal_prime_reason_codes
                ),
            )
        )
        if recovery_ready and family_hardening_reason_codes:
            recovery_ready = False
        recovery_status = str(
            health.get(
                "recoveryStatus",
                (
                    "global_execution_blocked"
                    if global_execution_reason_codes
                    else (
                        "family_hardening_restore_required"
                        if family_hardening_reason_codes
                        else (
                            "internal_prime_reconciliation_required"
                            if internal_prime_reason_codes
                            else (
                                "capital_truth_restore_required"
                                if (
                                    receipt_outcome_truth_reason_codes or capital_truth_reason_codes
                                )
                                else (
                                    "ready" if recovery_ready else "fund_summary_restore_required"
                                )
                            )
                        )
                    )
                ),
            )
        )
        if recovery_status == "ready" and family_hardening_reason_codes:
            recovery_status = "family_hardening_restore_required"
        if capital_truth_health.get("blocked", False):
            recovery_ready = False
            if recovery_status == "ready":
                recovery_status = str(
                    capital_truth_health.get("recoveryStatus") or "capital_truth_restore_required"
                )
            if not recovery_reason_codes:
                recovery_reason_codes = _unique_strings(
                    list(capital_truth_health.get("recoveryReasonCodes") or [])
                )
            if recovery_reason_code == "ok":
                recovery_reason_code = str(
                    capital_truth_health.get("recoveryReasonCode")
                    or capital_truth_reason_code
                    or capital_truth_freshness_reason_code
                    or "capital_truth_degraded"
                )
        suggested_next_action = str(
            health.get("suggestedNextAction") or health.get("recoveryNextAction") or ""
        )
        if not suggested_next_action and family_hardening_reason_codes:
            suggested_next_action = "restore_family_hardening"
        elif not suggested_next_action and receipt_outcome_truth_reason_codes:
            suggested_next_action = "restore_receipt_outcome_truth"
        elif not suggested_next_action and capital_truth_health.get("blocked", False):
            suggested_next_action = str(capital_truth_health.get("nextAction") or "")
        metadata = {
            "blocked": bool(
                global_execution_reason_codes
                or family_hardening_reason_codes
                or receipt_outcome_truth_reason_codes
                or capital_truth_reason_codes
                or internal_prime_reason_codes
                or hold_reason_codes
                or not recovery_ready
            ),
            "globalExecutionBlocked": bool(
                health.get("globalExecutionBlocked", bool(global_execution_reason_codes))
            ),
            "globalExecutionReasonCodes": global_execution_reason_codes,
            "familyHardeningReasonCodes": family_hardening_reason_codes,
            "familyHardeningReliabilityClass": family_hardening_reliability_class,
            "familyHardeningReliabilityReasonCode": family_hardening_reliability_reason_code,
            "familyHardeningReliabilityReasonCodes": family_hardening_reliability_reason_codes,
            "familyHardeningRecoveryHistoryStatus": family_hardening_recovery_history_status,
            "capitalTruthReasonCodes": capital_truth_reason_codes,
            "capitalTruthReasonCode": capital_truth_reason_code,
            "capitalTruthFreshnessClass": str(
                capital_truth_health.get("freshnessClass")
                or health.get("capitalTruthFreshnessClass")
                or ""
            ),
            "capitalTruthFreshnessReasonCode": capital_truth_freshness_reason_code,
            "capitalTruthFreshnessReasonCodes": capital_truth_freshness_reason_codes,
            "capitalTruthHealth": dict(capital_truth_health),
            "capitalTruthRecoveryHistoryStatus": str(
                capital_truth_health.get("recoveryHistoryStatus") or ""
            ),
            "capitalTruthReliabilityClass": str(capital_truth_health.get("reliabilityClass") or ""),
            "capitalTruthReliabilityReasonCode": str(
                capital_truth_health.get("reliabilityReasonCode") or ""
            ),
            "capitalTruthReliabilityReasonCodes": _unique_strings(
                list(capital_truth_health.get("reliabilityReasonCodes") or [])
            ),
            "receiptOutcomeTruthReasonCodes": receipt_outcome_truth_reason_codes,
            "receiptOutcomeTruthReliabilityClass": receipt_outcome_truth_reliability_class,
            "receiptOutcomeTruthReliabilityReasonCode": receipt_outcome_truth_reliability_reason_code,
            "receiptOutcomeTruthReliabilityReasonCodes": receipt_outcome_truth_reliability_reason_codes,
            "internalPrimeReasonCodes": internal_prime_reason_codes,
            "holdReasonCode": hold_reason_code,
            "holdReasonCodes": hold_reason_codes,
            "suggestedNextAction": suggested_next_action,
            "recoveryReady": recovery_ready,
            "recoveryStatus": recovery_status,
            "recoveryReasonCode": recovery_reason_code,
            "recoveryReasonCodes": recovery_reason_codes,
            "recoveryNextAction": str(health.get("recoveryNextAction") or suggested_next_action),
            "recoveryHistoryComponent": recovery_history_component,
            "recoveryHistoryStatus": recovery_history_status,
            "recoveryReliabilityClass": recovery_reliability_class,
            "recoveryReliabilityReasonCode": recovery_reliability_reason_code,
            "recoveryReliabilityReasonCodes": recovery_reliability_reason_codes,
        }
        if metadata["blocked"]:
            reason = (
                hold_reason_code
                or capital_truth_reason_code
                or capital_truth_freshness_reason_code
                or recovery_reason_code
                or "fund_hold_active"
            )
            return ExecutionGateResult(False, str(reason), metadata)
        return ExecutionGateResult(True, "ok", metadata)

    def auto_trade_execution_realism_gate(
        self, opp: Any, decision: Any | None, runtime: Any | None = None
    ) -> tuple[Any, ExecutionGateResult]:
        """Fail closed for auto-trading when route realism or after-fee truth is incomplete."""

        prepared_opp, prep_meta = self.prepare_execution_opportunity(opp, decision)
        route_reason = str(prep_meta.get("reason") or "")
        selected_venues = list(prep_meta.get("selectedVenues") or [])
        route_invalid_causes = _unique_strings(list(prep_meta.get("routeInvalidCauses") or []))
        provider_priority = list(prep_meta.get("providerPriority") or [])
        flashloan_sizing = dict(prep_meta.get("flashloanSizing") or {})

        metadata: Dict[str, Any] = {
            "blocked": False,
            "applied": bool(prep_meta.get("applied", False)),
            "reason_code": "ok",
            "reason_codes": [],
            "selectedVenues": selected_venues,
            "routeInvalidCauses": route_invalid_causes,
            "providerPriority": provider_priority,
            "flashloanSizing": flashloan_sizing,
            "suggestedNextAction": "continue_auto_trade",
        }
        if not metadata["applied"]:
            reason = route_reason or "execution_route_plan_unavailable"
            metadata.update(
                {
                    "blocked": True,
                    "reason_code": reason,
                    "reason_codes": [reason],
                    "suggestedNextAction": (
                        "refresh_execution_route_plan"
                        if reason == "route_plan_not_executable"
                        else "refresh_execution_capture"
                    ),
                }
            )
            return prepared_opp, ExecutionGateResult(False, str(reason), metadata)

        meta = _safe_dict(getattr(prepared_opp, "meta", None))
        route_truth = execution_route_truth(meta)
        route_runtime = _safe_dict(route_truth.get("runtime"))
        route_runtime_reason_codes = list(route_truth.get("runtime_reason_codes") or [])
        profit_after, profit_after_verified, profit_after_reason, profit_after_meta = (
            _profit_after_costs_gate_info(prepared_opp)
        )
        metadata.update(
            {
                "routeRuntime": route_runtime,
                "routeRuntimeDegraded": bool(route_truth.get("runtime_degraded", False)),
                "routeRuntimeReasonCodes": route_runtime_reason_codes,
                "profitAfterCostsWei": str(int(max(0, profit_after))),
                "profitAfterCostsVerified": bool(profit_after_verified),
                "profitAfterCostsReason": str(profit_after_reason or "ok"),
            }
        )
        metadata.update(dict(profit_after_meta))
        if bool(route_truth.get("runtime_degraded", False)):
            reason = str(route_truth.get("reason") or "execution_route_runtime_degraded")
            next_action = str(
                route_truth.get("suggested_next_action") or "refresh_execution_route_runtime"
            )
            metadata.update(
                {
                    "blocked": True,
                    "reason_code": str(reason),
                    "reason_codes": list(route_runtime_reason_codes or [reason]),
                    "suggestedNextAction": next_action,
                }
            )
            return prepared_opp, ExecutionGateResult(False, str(reason), metadata)
        if route_invalid_causes:
            reason = str(route_invalid_causes[0])
            metadata.update(
                {
                    "blocked": True,
                    "reason_code": reason,
                    "reason_codes": list(route_invalid_causes),
                    "suggestedNextAction": "refresh_execution_route_plan",
                }
            )
            return prepared_opp, ExecutionGateResult(False, reason, metadata)
        if not profit_after_verified:
            reason = str(profit_after_reason or "profit_after_costs_unavailable")
            metadata.update(
                {
                    "blocked": True,
                    "reason_code": reason,
                    "reason_codes": [reason],
                    "suggestedNextAction": "refresh_after_fee_profitability_truth",
                }
            )
            return prepared_opp, ExecutionGateResult(False, reason, metadata)
        capture_coordination = _capture_coordination_metadata(runtime, prepared_opp)
        metadata.update(dict(capture_coordination))
        capture_failure = _capture_coordination_failure(runtime, prepared_opp)
        if capture_failure:
            reason = str(capture_failure.get("reason") or "execution_capture_unavailable")
            metadata.update(
                {
                    "blocked": True,
                    "reason_code": reason,
                    "reason_codes": list(capture_failure.get("reason_codes") or [reason]),
                    "suggestedNextAction": str(
                        capture_failure.get("suggested_next_action") or "refresh_execution_capture"
                    ),
                }
            )
            metadata.update(dict(capture_failure.get("metadata") or {}))
            return prepared_opp, ExecutionGateResult(False, reason, metadata)
        return prepared_opp, ExecutionGateResult(True, "ok", metadata)

    def auto_trade_flashloan_gate(
        self, runtime: Any, opp: Any, decision: Any | None
    ) -> ExecutionGateResult:
        """Fail closed for auto-trading when flashloan sizing/provider truth is incomplete."""

        if not _is_flashloan_family(opp, decision):
            return ExecutionGateResult(True, "ok", {"blocked": False, "applicable": False})

        flashloan = _flashloan_metadata(opp, decision)
        sizing = _safe_dict(flashloan.get("sizing"))
        provider_priority = [
            str(x)
            for x in list(
                sizing.get("provider_priority") or flashloan.get("provider_priority") or []
            )
            if str(x)
        ]
        reason_codes = _unique_strings(list(sizing.get("reason_codes") or []))
        selected_provider = str(
            sizing.get("selected_provider") or flashloan.get("selected_provider") or ""
        )
        fallback_provider = str(
            sizing.get("fallback_provider") or flashloan.get("fallback_provider") or ""
        )
        metadata = {
            "blocked": False,
            "applicable": True,
            "family": _opportunity_family(opp),
            "selected_provider": selected_provider,
            "fallback_provider": fallback_provider,
            "provider_priority": provider_priority,
            "reason_code": "ok",
            "reason_codes": reason_codes,
            "allowed": sizing.get("allowed"),
            "size_mult": float(sizing.get("size_mult") or 1.0),
            "borrow_mult": float(sizing.get("borrow_mult") or 1.0),
            "provider_limit": float(sizing.get("provider_limit") or 0.0),
            "family_target_known": bool(sizing.get("family_target_known", True)),
            "resolved_family_target_key": str(sizing.get("resolved_family_target_key") or ""),
            "suggested_next_action": "continue_auto_trade",
        }
        if not sizing:
            metadata.update(
                {
                    "blocked": True,
                    "reason_code": "flashloan_sizing_unavailable",
                    "reason_codes": ["flashloan_sizing_unavailable"],
                    "suggested_next_action": "refresh_flashloan_eligibility_truth",
                }
            )
            return ExecutionGateResult(False, "flashloan_sizing_unavailable", metadata)
        if sizing.get("allowed") is not True:
            reason = str(reason_codes[0] if reason_codes else "flashloan_size_not_viable")
            metadata.update(
                {
                    "blocked": True,
                    "reason_code": reason,
                    "reason_codes": list(reason_codes or [reason]),
                    "suggested_next_action": "refresh_flashloan_eligibility_truth",
                }
            )
            return ExecutionGateResult(False, reason, metadata)
        if not selected_provider:
            metadata.update(
                {
                    "blocked": True,
                    "reason_code": "flashloan_provider_unavailable",
                    "reason_codes": ["flashloan_provider_unavailable"],
                    "suggested_next_action": "refresh_flashloan_provider_selection",
                }
            )
            return ExecutionGateResult(False, "flashloan_provider_unavailable", metadata)
        return ExecutionGateResult(True, "ok", metadata)

    def auto_trade_treasury_gate(self, runtime: Any) -> ExecutionGateResult:
        """Fail closed for auto-trading when enabled treasury governance blocks action."""

        treasury = getattr(runtime, "_treasury", None)
        cfg = getattr(treasury, "cfg", None) if treasury is not None else None
        enabled = bool(getattr(cfg, "enabled", False)) if cfg is not None else False
        if treasury is None or not enabled:
            return ExecutionGateResult(
                True,
                "ok",
                {
                    "applicable": False,
                    "enabled": enabled,
                    "blocked": False,
                },
            )

        try:
            if hasattr(treasury, "snapshot"):
                state = treasury.snapshot() or {}
            elif hasattr(treasury, "report_state"):
                state = treasury.report_state() or {}
            else:
                state = {}
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            return ExecutionGateResult(
                False,
                "treasury_state_unavailable",
                {
                    "applicable": True,
                    "enabled": True,
                    "blocked": True,
                    "reason_code": "treasury_state_unavailable",
                    "reason_codes": ["treasury_state_unavailable"],
                    "suggested_next_action": "refresh_treasury_state",
                    "detail": str(exc),
                },
            )

        state = _safe_dict(state)
        aggressiveness = _safe_dict(state.get("aggressiveness"))
        goal = _safe_dict(state.get("goal"))
        level = str(aggressiveness.get("aggressiveness_level") or "").upper()
        if not level:
            return ExecutionGateResult(
                False,
                "treasury_aggressiveness_unavailable",
                {
                    "applicable": True,
                    "enabled": True,
                    "blocked": True,
                    "reason_code": "treasury_aggressiveness_unavailable",
                    "reason_codes": ["treasury_aggressiveness_unavailable"],
                    "suggested_next_action": "refresh_treasury_state",
                },
            )

        approved = bool(
            state.get("approved_by_human")
            or state.get("governance_approved")
            or _safe_dict(state.get("governance")).get("approved_by_human")
        )
        urgency_factor = float(aggressiveness.get("urgency_factor") or 0.0)
        raw_borrow_cap = float((state.get("borrow_mult_target_cap") or 1.0) or 1.0)
        try:
            gov = treasury.governance_contract(
                aggressiveness_level=level,
                borrow_mult_target_cap=raw_borrow_cap,
                urgency_factor=urgency_factor,
                approved_by_human=approved,
            )
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            try:
                raw_gov = treasury.governance_check(
                    aggressiveness_level=level,
                    approved_by_human=approved,
                )
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
                raw_gov = treasury_governance_view(state)
            max_without = str(
                getattr(cfg, "max_aggressiveness_without_approval", "HIGH") or "HIGH"
            ).upper()
            if max_without not in {"LOW", "MODERATE", "HIGH", "MAXIMUM"}:
                max_without = "HIGH"
            allow_maximum = bool(getattr(cfg, "allow_maximum", False))
            effective_level = level
            if not approved:
                if effective_level == "MAXIMUM" and not allow_maximum:
                    effective_level = "HIGH"
                if _level_rank(effective_level) > _level_rank(max_without):
                    effective_level = max_without
            reason = str(raw_gov.get("reason") or "ok")
            blocked = not bool(raw_gov.get("ok", False))
            gov = {
                "ok": not blocked,
                "blocked": blocked,
                "reason": reason,
                "reason_codes": ([] if reason == "ok" else [reason]),
                "approved_by_human": approved,
                "allow_maximum": allow_maximum,
                "max_aggressiveness_without_approval": max_without,
                "raw_aggressiveness_level": level,
                "effective_aggressiveness_level": effective_level,
                "raw_borrow_mult_target_cap": raw_borrow_cap,
                "effective_borrow_mult_target_cap": (1.0 if blocked else raw_borrow_cap),
                "urgency_factor": urgency_factor,
                "suggested_next_action": (
                    "continue_treasury_plan"
                    if reason == "ok"
                    else (
                        "lower_treasury_aggressiveness_or_enable_maximum"
                        if reason == "maximum_disabled"
                        else "obtain_treasury_approval_or_reduce_aggressiveness"
                    )
                ),
            }

        reason = str(gov.get("reason") or "ok")
        metadata = {
            "applicable": True,
            "enabled": True,
            "blocked": bool(gov.get("blocked", False)),
            "aggressiveness_level": level,
            "effective_aggressiveness_level": str(
                gov.get("effective_aggressiveness_level") or level
            ),
            "aggressiveness_multiplier": float(
                aggressiveness.get("aggressiveness_multiplier") or 1.0
            ),
            "current_return_pct": float(aggressiveness.get("current_return_pct") or 0.0),
            "performance_gap": float(aggressiveness.get("performance_gap") or 0.0),
            "urgency_factor": float(aggressiveness.get("urgency_factor") or 0.0),
            "drawdown_pct": float(aggressiveness.get("drawdown_pct") or 0.0),
            "target_return_percentage": float(goal.get("target_return_percentage") or 0.0),
            "max_drawdown_pct": float(goal.get("max_drawdown_pct") or 0.0),
            "approved_by_human": bool(gov.get("approved_by_human", approved)),
            "allow_maximum": bool(gov.get("allow_maximum", getattr(cfg, "allow_maximum", False))),
            "max_aggressiveness_without_approval": str(
                gov.get("max_aggressiveness_without_approval")
                or getattr(cfg, "max_aggressiveness_without_approval", "HIGH")
                or "HIGH"
            ).upper(),
            "borrow_mult_target_cap": raw_borrow_cap,
            "effective_borrow_mult_target_cap": float(
                gov.get("effective_borrow_mult_target_cap") or raw_borrow_cap
            ),
            "reason_code": reason,
            "reason_codes": list(gov.get("reason_codes") or ([] if reason == "ok" else [reason])),
            "suggested_next_action": str(
                gov.get("suggested_next_action") or "continue_treasury_plan"
            ),
            "governance": dict(gov),
        }
        if bool(gov.get("blocked", False)):
            return ExecutionGateResult(False, reason, metadata)
        return ExecutionGateResult(True, "ok", metadata)

    def auto_trade_admission_gate(
        self, runtime: Any, opp: Any, decision: Any | None = None
    ) -> AutoTradeAdmissionResult:
        current_opp = opp
        plan: Dict[str, Any] = {}
        try:
            hold_gate = self.auto_trade_hold_gate(runtime)
            hold_reason = str(
                getattr(hold_gate, "reason", "fund_hold_active") or "fund_hold_active"
            )
            hold_meta = _normalize_admission_gate_metadata(
                getattr(hold_gate, "metadata", {}) or {}, reason=hold_reason
            )
            plan["hold"] = dict(hold_meta)
            if not bool(getattr(hold_gate, "allowed", False)):
                return AutoTradeAdmissionResult(
                    False,
                    "fund_hold",
                    hold_reason,
                    current_opp,
                    dict(hold_meta),
                    dict(plan),
                )

            family_gate = self.auto_trade_family_gate(runtime, current_opp)
            family_reason = str(
                getattr(family_gate, "reason", "family_not_ready") or "family_not_ready"
            )
            family_meta = _normalize_admission_gate_metadata(
                getattr(family_gate, "metadata", {}) or {}, reason=family_reason
            )
            plan["family"] = dict(family_meta)
            if not bool(getattr(family_gate, "allowed", False)):
                return AutoTradeAdmissionResult(
                    False,
                    "family_hold",
                    family_reason,
                    current_opp,
                    dict(family_meta),
                    dict(plan),
                )

            current_opp, route_gate = self.auto_trade_execution_realism_gate(
                current_opp, decision, runtime
            )
            route_reason = str(
                getattr(route_gate, "reason", "execution_route_plan_unavailable")
                or "execution_route_plan_unavailable"
            )
            route_meta = _normalize_admission_gate_metadata(
                getattr(route_gate, "metadata", {}) or {}, reason=route_reason
            )
            plan["route"] = dict(route_meta)
            if not bool(getattr(route_gate, "allowed", False)):
                return AutoTradeAdmissionResult(
                    False,
                    "route_hold",
                    route_reason,
                    current_opp,
                    dict(route_meta),
                    dict(plan),
                )

            flashloan_gate = self.auto_trade_flashloan_gate(runtime, current_opp, decision)
            flashloan_reason = str(
                getattr(flashloan_gate, "reason", "flashloan_sizing_unavailable")
                or "flashloan_sizing_unavailable"
            )
            flashloan_meta = _normalize_admission_gate_metadata(
                getattr(flashloan_gate, "metadata", {}) or {}, reason=flashloan_reason
            )
            plan["flashloan"] = dict(flashloan_meta)
            if not bool(getattr(flashloan_gate, "allowed", False)):
                return AutoTradeAdmissionResult(
                    False,
                    "flashloan_hold",
                    flashloan_reason,
                    current_opp,
                    dict(flashloan_meta),
                    dict(plan),
                )

            treasury_gate = self.auto_trade_treasury_gate(runtime)
            treasury_reason = str(
                getattr(treasury_gate, "reason", "treasury_state_unavailable")
                or "treasury_state_unavailable"
            )
            treasury_meta = _normalize_admission_gate_metadata(
                getattr(treasury_gate, "metadata", {}) or {}, reason=treasury_reason
            )
            plan["treasury"] = dict(treasury_meta)
            if not bool(getattr(treasury_gate, "allowed", False)):
                return AutoTradeAdmissionResult(
                    False,
                    "treasury_hold",
                    treasury_reason,
                    current_opp,
                    dict(treasury_meta),
                    dict(plan),
                )
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            gate = {
                "blocked": True,
                "reason_code": "admission_gate_failed",
                "reason_codes": ["admission_gate_failed"],
                "suggested_next_action": "restore_auto_trade_admission_state",
                "detail": str(exc),
            }
            plan["admission"] = dict(gate)
            return AutoTradeAdmissionResult(
                False,
                "admission_hold",
                "admission_gate_failed",
                current_opp,
                gate,
                dict(plan),
            )

        return AutoTradeAdmissionResult(
            True,
            "ok",
            "ok",
            current_opp,
            {
                "blocked": False,
                "reason_code": "ok",
                "reason_codes": [],
                "suggested_next_action": "",
            },
            dict(plan),
        )

    def handle_auto_trade_admission(
        self, runtime: Any, opp: Any, decision: Any | None, *, force_dry_run: bool
    ) -> AutoTradeAdmissionHandlingResult:
        try:
            admission = self.auto_trade_admission_gate(runtime, opp, decision)
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            failed, admission = _admission_failure_result(
                opp, force_dry_run=force_dry_run, detail=str(exc)
            )
            _observe_auto_trade_recovery(runtime, admission)
            return failed

        _observe_auto_trade_recovery(runtime, admission)
        opportunity = getattr(admission, "opportunity", opp)
        if bool(getattr(admission, "allowed", False)):
            return AutoTradeAdmissionHandlingResult(opportunity=opportunity, blocked_result=None)

        stage = str(getattr(admission, "stage", "execution_hold") or "execution_hold")
        reason = str(getattr(admission, "reason", "execution_hold") or "execution_hold")
        return AutoTradeAdmissionHandlingResult(
            opportunity=opportunity,
            blocked_result=ExecResult(
                False,
                bool(force_dry_run),
                f"{stage}:{reason}",
                attempted=False,
                plan=dict(getattr(admission, "plan", {}) or {}),
            ),
        )

    def handle_governance_pre_execute(
        self, runtime: Any, opp: Any, bn: int, decision: Any | None, *, force_dry_run: bool
    ) -> GovernancePreExecuteResult:
        try:
            overlay = (
                opp.meta.get("overlay") if isinstance(getattr(opp, "meta", None), dict) else {}
            ) or {}
            if getattr(runtime, "_consensus", None) is not None:
                en = getattr(
                    getattr(runtime.cfg.execution, "consensus", None), "enforce_on_auto", True
                )
                if bool(en) and not bool(overlay.get("consensus_allow", True)):
                    return GovernancePreExecuteResult(
                        opportunity=opp,
                        blocked_result=ExecResult(
                            False,
                            bool(force_dry_run),
                            "consensus_rejected",
                            attempted=False,
                        ),
                    )
        except _SAFE_RUNTIME_EXCEPTIONS:
            pass

        try:
            cc_gov_ok = True
            try:
                if getattr(runtime, "_cc", None) is not None:
                    cc_gov_ok = bool(
                        getattr(getattr(runtime._cc, "controls", None), "governance_enabled", True)
                    )
            except (AttributeError, KeyError, TypeError, ValueError):
                cc_gov_ok = True

            if (
                cc_gov_ok
                and getattr(runtime, "_gov", None) is not None
                and bool(getattr(runtime.cfg.execution.governance, "enforce_on_auto", True))
            ):
                legs = int(len(getattr(getattr(opp, "route", None), "legs", []) or []))
                stype = "dex_flash_3leg" if legs >= 3 else "dex_flash_2leg"
                mr = float(
                    ((opp.meta or {}).get("margin_ratio") or 0.0)
                    if isinstance(getattr(opp, "meta", None), dict)
                    else 0.0
                )
                risk_profile = (
                    "aggressive"
                    if float(getattr(decision, "borrow_mult", 1.0) or 1.0) > 1.25
                    else "moderate"
                )
                tg = BUS.snapshot().get("treasury") if isinstance(BUS.snapshot(), dict) else {}
                tg = tg or {}
                try:
                    rp2 = str(
                        ((tg.get("goal") or {}) if isinstance(tg.get("goal"), dict) else {}).get(
                            "risk_tolerance"
                        )
                        or ""
                    ).lower()
                    if rp2 in {"conservative", "moderate", "aggressive"}:
                        risk_profile = rp2
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    pass

                intent = runtime._gov.generate_intent(
                    seed=f"{int(bn)}:{str(getattr(opp, 'id', '') or '')}",
                    agent_id="ARBITRAGE_AGENT",
                    strategy_type=stype,
                    objective={"profit": "maximize", "mode": "auto"},
                    parameters={
                        "opportunity_id": str(getattr(opp, "id", "")),
                        "route_id": str(getattr(opp, "route_id", "")),
                        "gas_mode": str(
                            getattr(decision, "gas_mode", runtime.cfg.execution.gas_mode)
                            or runtime.cfg.execution.gas_mode
                        ),
                        "size_mult": float(getattr(decision, "size_mult", 1.0) or 1.0),
                        "borrow_mult": float(getattr(decision, "borrow_mult", 1.0) or 1.0),
                    },
                    expected_edge=float(mr),
                    risk_profile=str(risk_profile),
                    capital_allocation=float(
                        min(
                            1.0,
                            max(
                                0.0,
                                float(getattr(decision, "size_mult", 1.0) or 1.0)
                                * float(getattr(decision, "borrow_mult", 1.0) or 1.0)
                                / 5.0,
                            ),
                        )
                    ),
                    execution_constraints={
                        "max_slippage": int(getattr(runtime.cfg.safety, "slippage_bps", 50) or 50),
                        "max_gas": int(
                            getattr(runtime.cfg.execution, "daily_gas_budget_wei", "0") or "0"
                        ),
                        "time_bound": int(time.time()) + 60,
                    },
                    governance_tags={
                        "regulatory_risk_score": 0.0,
                        "mev_exposure_score": float(overlay.get("mev_risk", 0.0) or 0.0),
                    },
                )
                gate = runtime._gov.governance_check(
                    intent=intent,
                    meta={
                        "margin_ratio": mr,
                        "will_simulate": bool(
                            getattr(runtime.cfg.execution, "dry_run", True)
                            or bool(getattr(runtime.cfg.safety, "require_simulation", False))
                        ),
                        **dict(overlay),
                    },
                    simulation_result=None,
                    text_inputs="",
                    multi_agent_bundle_detected=bool(getattr(decision, "portfolio", None)),
                )
                if not bool(gate.get("ok", False)):
                    return GovernancePreExecuteResult(
                        opportunity=opp,
                        blocked_result=ExecResult(
                            False,
                            bool(force_dry_run),
                            f"governance_rejected:{gate.get('reason','')}:{gate.get('outcome','')}",
                            attempted=False,
                        ),
                    )
                try:
                    runtime._gov.approve_intent(intent_id=str(intent.intent_id), reviewer="agent")
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    pass
                try:
                    if isinstance(opp.meta, dict):
                        opp.meta["intent_id"] = str(intent.intent_id)
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    pass
        except _SAFE_RUNTIME_EXCEPTIONS:
            pass

        return GovernancePreExecuteResult(opportunity=opp, blocked_result=None)

    async def handle_fioa_execution_wrapper(
        self, runtime: Any, opp: Any, decision: Any | None, core_coro: Callable[[], Awaitable[Any]]
    ) -> Any:
        fioa = getattr(runtime, "_fioa", None)
        if fioa is None or not bool(getattr(getattr(fioa, "cfg", None), "enabled", False)):
            return await core_coro()

        try:
            cap, risk = fioa.estimate_trade_context(runtime, opp, decision=decision)
        except _SAFE_RUNTIME_EXCEPTIONS:
            cap, risk = 0.0, 0.0

        return await fioa.execution_wrapper(
            core_coro,
            agent_id="ARBITRAGE_AGENT",
            action_type=str(
                getattr(fioa, "TRADE_EXECUTION", "TRADE_EXECUTION") or "TRADE_EXECUTION"
            ),
            capital=float(cap),
            risk=float(risk),
            data_level=str(
                getattr(fioa, "INTERNAL_STRATEGY", "INTERNAL_STRATEGY") or "INTERNAL_STRATEGY"
            ),
            core_command="try_execute_opportunity",
            mode="auto",
            meta={
                "opportunity_id": str(getattr(opp, "id", "") or ""),
                "route_id": str(getattr(opp, "route_id", "") or ""),
            },
        )

    async def handle_post_execute_bookkeeping(
        self,
        runtime: Any,
        opp: Any,
        result: ExecResult,
        *,
        bn: int,
        latency_ms: int,
        mode: str,
    ) -> None:
        try:
            cc_lat_ok = True
            try:
                if getattr(runtime, "_cc", None) is not None:
                    controls = getattr(runtime._cc, "controls", None)
                    if controls is not None and not bool(
                        getattr(controls, "latency_profiling_enabled", True)
                    ):
                        cc_lat_ok = False
            except (AttributeError, KeyError, TypeError, ValueError):
                cc_lat_ok = True

            lat = getattr(runtime, "_lat", None)
            if cc_lat_ok and lat is not None:
                stages = (
                    (getattr(result, "plan", None) or {}).get("latency_stages_ms")
                    if isinstance(getattr(result, "plan", None), dict)
                    else None
                )
                if isinstance(stages, dict) and "total" in stages:
                    lat.add("exec_e2e_ms", float(stages.get("total") or latency_ms))
                else:
                    lat.add("exec_e2e_ms", float(latency_ms))
                summary = lat.get("exec_e2e_ms")
                runtime.metrics.exec_e2e_p50_ms = float(summary.get("p50", 0.0) or 0.0)
                runtime.metrics.exec_e2e_p90_ms = float(summary.get("p90", 0.0) or 0.0)
                runtime.metrics.exec_e2e_p99_ms = float(summary.get("p99", 0.0) or 0.0)
        except (AttributeError, KeyError, TypeError, ValueError):
            pass

        await runtime._record_exec(result, opp, latency_ms=latency_ms, mode=mode)
        if result.ok and (not result.dry_run) and getattr(result, "submitted", False):
            runtime._last_submitted_block = bn
            runtime.metrics.last_submitted_block = bn

    def handle_superstructure_pre_execute(
        self, runtime: Any, opp: Any, decision: Any | None, *, force_dry_run: bool
    ) -> SuperstructurePreExecuteResult:
        super_enabled = (
            bool(
                getattr(getattr(runtime, "_super", None), "cfg", None)
                and getattr(runtime._super.cfg, "enabled", False)
            )
            if getattr(runtime, "_super", None) is not None
            else False
        )
        old_gas_mode = str(getattr(runtime.cfg.execution, "gas_mode", "standard") or "standard")
        old_send_mode = str(getattr(runtime.cfg.execution, "send_mode", "public") or "public")

        if not super_enabled:
            return SuperstructurePreExecuteResult(
                opportunity=opp,
                blocked_result=None,
                super_enabled=False,
                old_gas_mode=old_gas_mode,
                old_send_mode=old_send_mode,
            )

        try:
            gate = runtime._super.pre_execute_trade(
                opp=opp,
                decision=decision,
                mode="auto",
                current_gas_mode=old_gas_mode,
                current_send_mode=old_send_mode,
            )
            if not bool(gate.get("allow", True)):
                return SuperstructurePreExecuteResult(
                    opportunity=opp,
                    blocked_result=ExecResult(
                        False,
                        bool(force_dry_run),
                        f"negotiation_rejected:{gate.get('reason','')}",
                        attempted=False,
                    ),
                    super_enabled=True,
                    old_gas_mode=old_gas_mode,
                    old_send_mode=old_send_mode,
                )

            scaled_opp = opp
            sm = float(gate.get("size_mult", 1.0) or 1.0)
            if 0.0 < sm < 1.0:
                scaled_opp = ExecutionService.scale_opportunity(self, opp, sm)
            _apply_superstructure_planner_overrides(runtime, gate.get("overrides") or {})
            return SuperstructurePreExecuteResult(
                opportunity=scaled_opp,
                blocked_result=None,
                super_enabled=True,
                old_gas_mode=old_gas_mode,
                old_send_mode=old_send_mode,
            )
        except _SAFE_RUNTIME_EXCEPTIONS:
            return SuperstructurePreExecuteResult(
                opportunity=opp,
                blocked_result=None,
                super_enabled=True,
                old_gas_mode=old_gas_mode,
                old_send_mode=old_send_mode,
            )

    def auto_trade_family_gate(self, runtime: Any, opp: Any) -> ExecutionGateResult:
        """Fail closed for auto-trading when canonical family rollout/readiness blocks action."""

        family = _opportunity_family(opp)
        try:
            service = getattr(runtime, "_family_hardening_service", None)
            if service is None or not hasattr(service, "family_state"):
                return ExecutionGateResult(
                    False,
                    "family_hardening_unavailable",
                    _family_hardening_gate_unavailable_metadata(family),
                )
            state = service.family_state(runtime, family)
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            return ExecutionGateResult(
                False,
                "family_hardening_unavailable",
                _family_hardening_gate_unavailable_metadata(family, detail=str(exc)),
            )

        if not isinstance(state, dict):
            return ExecutionGateResult(
                False,
                "family_hardening_unavailable",
                _family_hardening_gate_unavailable_metadata(
                    family, detail="invalid_family_hardening_state"
                ),
            )

        controls = _safe_dict(_safe_dict(state).get("controls"))
        explanation = _safe_dict(_safe_dict(state).get("explanation"))
        readiness = _safe_dict(_safe_dict(state).get("readiness"))
        enabled = bool(state.get("enabled", is_core_launch_family(family)))

        reason_codes = _unique_strings(
            list(controls.get("no_trade_reason_codes") or [])
            + list(controls.get("execution_reason_codes") or [])
            + list(controls.get("admission_reason_codes") or [])
            + list(controls.get("capital_reason_codes") or [])
            + list(controls.get("treasury_reason_codes") or [])
            + list(controls.get("governance_reason_codes") or [])
            + list(explanation.get("recovery_reason_codes") or [])
            + list(readiness.get("blockers") or [])
        )
        if not enabled and "family_not_active" not in reason_codes:
            reason_codes.insert(0, "family_not_active")

        blocked = bool(
            not enabled
            or controls.get("no_trade", False)
            or not bool(controls.get("admission_ready", readiness.get("ready", False)))
            or not bool(
                controls.get("execution_eligible", readiness.get("actualExecutionReady", False))
            )
            or not bool(controls.get("capital_eligible", True))
            or not bool(controls.get("treasury_eligible", True))
            or not bool(controls.get("governance_eligible", True))
            or not bool(controls.get("recovery_ready", explanation.get("recovery_ready", True)))
        )
        reason = (
            (reason_codes[0] if reason_codes else "")
            or ("family_not_active" if not enabled else "")
            or str(explanation.get("reason_code") or "family_not_ready")
        )
        metadata = {
            "blocked": blocked,
            "family": family,
            "enabled": enabled,
            "status": str(explanation.get("status") or readiness.get("status") or "blocked"),
            "reason_code": str(reason),
            "reason_codes": reason_codes,
            "admission_ready": bool(controls.get("admission_ready", readiness.get("ready", False))),
            "execution_eligible": bool(
                controls.get("execution_eligible", readiness.get("actualExecutionReady", False))
            ),
            "capital_eligible": bool(controls.get("capital_eligible", True)),
            "treasury_eligible": bool(controls.get("treasury_eligible", True)),
            "governance_eligible": bool(controls.get("governance_eligible", True)),
            "recovery_ready": bool(
                controls.get("recovery_ready", explanation.get("recovery_ready", True))
            ),
            "suggested_next_action": str(
                explanation.get("suggested_next_action")
                or explanation.get("recovery_next_action")
                or readiness.get("suggestedNextAction")
                or "stabilize_family_before_auto_trade"
            ),
        }
        if blocked:
            return ExecutionGateResult(False, str(reason), metadata)
        return ExecutionGateResult(True, "ok", metadata)

    def apply_operator_overrides(
        self, runtime: Any, opp: Any, *, force_dry_run: bool = False
    ) -> Tuple[Any, bool, str, str]:
        ctx = build_execution_runtime_signals(runtime)
        old_gas_mode = str(ctx.gas_mode)
        old_send_mode = str(ctx.send_mode)
        controls = ctx.controls
        if controls is not None:
            fgm = str(getattr(controls, "force_gas_mode", "") or "").strip().lower()
            fsm = str(getattr(controls, "force_send_mode", "") or "").strip().lower()
            if fgm in {"standard", "fast", "instant"}:
                runtime.cfg.execution.gas_mode = fgm
                runtime.metrics.gas_mode = fgm
            if fsm in {"public", "private", "protected_rpc"}:
                runtime.cfg.execution.send_mode = fsm
                runtime.metrics.send_mode = fsm
        return opp, force_dry_run, old_gas_mode, old_send_mode

    def restore_operator_overrides(
        self, runtime: Any, *, old_gas_mode: str, old_send_mode: str
    ) -> None:
        try:
            runtime.cfg.execution.gas_mode = old_gas_mode
            runtime.metrics.gas_mode = old_gas_mode
            runtime.cfg.execution.send_mode = old_send_mode
            runtime.metrics.send_mode = old_send_mode
        except (AttributeError, KeyError, TypeError, ValueError):
            pass

    def prepare_execution(self, opp: Any, decision: Any | None) -> ExecutionPreparationResult:
        capture_meta = (
            dict((getattr(opp, "meta", {}) or {}).get("capture") or {})
            if isinstance(getattr(opp, "meta", None), dict)
            else {}
        )
        metadata = (
            dict(getattr(decision, "metadata", {}) or capture_meta.get("metadata") or {})
            if decision is not None
            else dict(capture_meta.get("metadata") or {})
        )
        execution_plan = dict(metadata.get("execution_route_plan") or {})
        if not execution_plan:
            return ExecutionPreparationResult(
                opportunity=opp, metadata={"applied": False, "reason": "no_execution_route_plan"}
            )
        if not bool(execution_plan.get("executable", True)):
            return ExecutionPreparationResult(
                opportunity=opp,
                metadata={
                    "applied": False,
                    "reason": "route_plan_not_executable",
                    "routeInvalidCauses": list(execution_plan.get("route_invalid_causes") or []),
                },
            )
        try:
            mutated = apply_execution_route_plan(opp=opp, plan=execution_plan)
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            return ExecutionPreparationResult(
                opportunity=opp,
                metadata={
                    "applied": False,
                    "reason": f"route_mutation_failed:{e}",
                    "routeInvalidCauses": list(execution_plan.get("route_invalid_causes") or []),
                },
            )
        return ExecutionPreparationResult(
            opportunity=mutated,
            metadata={
                "applied": True,
                "routeInvalidCauses": list(execution_plan.get("route_invalid_causes") or []),
                "selectedVenues": list(execution_plan.get("selected_venues") or []),
                "providerPriority": list(execution_plan.get("provider_priority") or []),
                "flashloanSizing": dict(
                    (
                        (
                            (getattr(decision, "metadata", {}) or {}).get("flashloan_resilience")
                            or {}
                        ).get("sizing")
                        or {}
                    )
                    if decision is not None
                    and isinstance(getattr(decision, "metadata", None), dict)
                    else {}
                ),
            },
        )

    def prepare_execution_opportunity(
        self, opp: Any, decision: Any | None
    ) -> tuple[Any, Dict[str, Any]]:
        result = self.prepare_execution(opp, decision)
        return result.opportunity, result.metadata

    def _sync_post_mutation_revalidation(
        self,
        opp: Any,
        *,
        route_context: Dict[str, Any] | None = None,
        source: str = "execution_service",
    ) -> Dict[str, Any]:
        if not has_profitability_contract(opp):
            return {}
        try:
            return dict(
                refresh_post_mutation_revalidation_contract(
                    opp,
                    getattr(getattr(opp, "meta", {}), "cfg", None),
                    stage="post_mutation_submission_gate",
                    source=source,
                    route_context=dict(route_context or {}),
                )
            )
        except _EXECUTION_PLAN_FAILURES:
            cfg = None
            try:
                cfg = getattr(opp, "_execution_cfg", None)
            except _SAFE_RUNTIME_EXCEPTIONS:
                cfg = None
            if cfg is None:
                return {}
            try:
                return dict(
                    refresh_post_mutation_revalidation_contract(
                        opp,
                        cfg,
                        stage="post_mutation_submission_gate",
                        source=source,
                        route_context=dict(route_context or {}),
                    )
                )
            except _EXECUTION_PLAN_FAILURES:
                return {}

    def refresh_pre_execution_profitability(
        self, runtime: Any, opp: Any, *, route_context: Dict[str, Any] | None = None
    ) -> tuple[Any, Dict[str, Any]]:
        if not has_profitability_contract(opp):
            return opp, {}
        contract = refresh_post_mutation_revalidation_contract(
            opp,
            runtime.cfg,
            stage="post_mutation_submission_gate",
            source="execution_service",
            route_context=dict(route_context or {}),
        )
        profitability = dict(contract.get("profitability") or {})
        out = dict(contract)
        out["profitability"] = profitability
        out["authoritative"] = bool(contract.get("authoritative", False))
        out["valid"] = bool(contract.get("valid", False))
        out["reason"] = str(contract.get("reason_code") or profitability.get("reason") or "ok")
        out["reason_code"] = str(contract.get("reason_code") or profitability.get("reason") or "ok")
        return opp, out

    def prepare_auto_execution(
        self, runtime: Any, opp: Any, *, bn: int, decision: Any | None = None
    ) -> AutoExecutionPreflightResult:
        force_dry = False
        old_gas_mode = str(getattr(runtime.cfg.execution, "gas_mode", ""))
        old_send_mode = str(getattr(runtime.cfg.execution, "send_mode", ""))
        try:
            cc = getattr(runtime, "_cc", None)
            controls = getattr(cc, "controls", None) if cc is not None else None
            if controls is not None and bool(getattr(controls, "paused", False)):
                return AutoExecutionPreflightResult(
                    False,
                    opp,
                    decision,
                    False,
                    old_gas_mode,
                    old_send_mode,
                    "",
                    "",
                    ExecResult(False, True, "cc_paused", attempted=False),
                    {"reason": "cc_paused"},
                )
            if controls is not None and bool(getattr(controls, "sandbox_only", False)):
                force_dry = True
            if controls is not None and (
                bool(getattr(controls, "defensive_mode", False))
                or bool(getattr(controls, "reduce_exposure_half", False))
            ):
                try:
                    if decision is not None:
                        setattr(
                            decision,
                            "size_mult",
                            min(float(getattr(decision, "size_mult", 1.0) or 1.0), 0.5),
                        )
                        setattr(
                            decision,
                            "borrow_mult",
                            min(float(getattr(decision, "borrow_mult", 1.0) or 1.0), 1.0),
                        )
                except (AttributeError, TypeError, ValueError):
                    pass
        except _SAFE_RUNTIME_EXCEPTIONS:
            pass
        send_url = runtime.rpc_manager.best_send()
        if str(getattr(runtime.cfg.execution, "send_mode", "public")) in {
            "private",
            "protected_rpc",
        }:
            send_url = runtime.rpc_manager.best_private() or send_url
        read_url = runtime.rpc_manager.best_read()
        if not send_url or not read_url:
            return AutoExecutionPreflightResult(
                False,
                opp,
                decision,
                force_dry,
                old_gas_mode,
                old_send_mode,
                str(send_url or ""),
                str(read_url or ""),
                None,
                {"reason": "rpc_unavailable"},
            )

        opp, exec_plan_meta = self.prepare_execution_opportunity(opp, decision)
        if (
            not bool(exec_plan_meta.get("applied", True))
            and str(exec_plan_meta.get("reason") or "") != "no_execution_route_plan"
        ):
            return AutoExecutionPreflightResult(
                False,
                opp,
                decision,
                force_dry,
                old_gas_mode,
                old_send_mode,
                str(send_url),
                str(read_url),
                None,
                dict(exec_plan_meta),
            )

        opp, profitability_meta = self.refresh_pre_execution_profitability(
            runtime, opp, route_context=dict(exec_plan_meta)
        )
        profitability_payload = (
            dict(profitability_meta.get("profitability") or {})
            if isinstance(profitability_meta.get("profitability"), dict)
            else {}
        )
        profitability_reason = str(
            profitability_meta.get("reason_code") or profitability_payload.get("reason") or ""
        )
        if (
            has_profitability_contract(opp)
            and profitability_reason != "gas_cost_unavailable"
            and (
                (not bool(profitability_meta.get("authoritative", False)))
                or (not bool(profitability_meta.get("valid", False)))
            )
        ):
            reason = str(profitability_meta.get("reason") or "profitability_unavailable")
            return AutoExecutionPreflightResult(
                False,
                opp,
                decision,
                force_dry,
                old_gas_mode,
                old_send_mode,
                str(send_url),
                str(read_url),
                None,
                {
                    **dict(exec_plan_meta),
                    "reason": f"profitability_contract:{reason}",
                    "profitability": dict(profitability_payload or profitability_meta),
                    "postMutationRevalidation": dict(profitability_meta),
                },
            )

        capital_admission_meta = {}
        service = getattr(runtime, "_capital_admission_service", None)
        if service is not None:
            try:
                capital_admission = service.evaluate(runtime, opp, decision=decision)
                capital_admission_meta = (
                    capital_admission.to_dict()
                    if hasattr(capital_admission, "to_dict")
                    else dict(capital_admission or {})
                )
                details = (
                    dict(capital_admission_meta.get("details") or {})
                    if isinstance(capital_admission_meta.get("details"), dict)
                    else {}
                )
                details["postMutationRevalidation"] = dict(profitability_meta)
                capital_admission_meta["details"] = details
                if isinstance(getattr(opp, "meta", None), dict):
                    opp.meta["capital_admission"] = dict(capital_admission_meta)
                if not bool(
                    getattr(
                        capital_admission, "allowed", capital_admission_meta.get("allowed", False)
                    )
                ):
                    blocked = ExecResult(
                        False,
                        bool(runtime.cfg.execution.dry_run or force_dry),
                        f"capital_admission:{capital_admission_meta.get('reason_code') or capital_admission_meta.get('reason') or 'denied'}",
                        attempted=False,
                        plan={"capitalAdmission": dict(capital_admission_meta)},
                    )
                    return AutoExecutionPreflightResult(
                        False,
                        opp,
                        decision,
                        force_dry,
                        old_gas_mode,
                        old_send_mode,
                        str(send_url),
                        str(read_url),
                        blocked,
                        {
                            **dict(exec_plan_meta),
                            "reason": str(
                                capital_admission_meta.get("reason_code")
                                or capital_admission_meta.get("reason")
                                or "capital_denied"
                            ),
                            "profitability": dict(profitability_payload or profitability_meta),
                            "postMutationRevalidation": dict(profitability_meta),
                            "capitalAdmission": dict(capital_admission_meta),
                        },
                    )
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                blocked = ExecResult(
                    False,
                    bool(runtime.cfg.execution.dry_run or force_dry),
                    f"capital_admission_error:{exc}",
                    attempted=False,
                )
                return AutoExecutionPreflightResult(
                    False,
                    opp,
                    decision,
                    force_dry,
                    old_gas_mode,
                    old_send_mode,
                    str(send_url),
                    str(read_url),
                    blocked,
                    {**dict(exec_plan_meta), "reason": "capital_admission_error"},
                )

        return AutoExecutionPreflightResult(
            True,
            opp,
            decision,
            force_dry,
            old_gas_mode,
            old_send_mode,
            str(send_url),
            str(read_url),
            None,
            {
                **dict(exec_plan_meta),
                "profitability": dict(profitability_payload or profitability_meta),
                "postMutationRevalidation": dict(profitability_meta),
                "capitalAdmission": dict(capital_admission_meta),
            },
        )

    def _sync_terminal_profitability_authority(self, opp: Any, result: ExecResult) -> None:
        plan = getattr(result, "plan", None)
        if not isinstance(plan, dict):
            return
        profitability = dict(plan.get("profitability") or {})
        if not profitability:
            profitability = profitability_state_view(opp)
        if not profitability:
            return
        authority = build_terminal_profitability_authority(profitability, source="execution_plan")
        plan["terminalProfitabilityAuthority"] = dict(authority)
        if isinstance(getattr(opp, "meta", None), dict):
            set_profitability_state(opp, profitability)
            opp.meta["terminal_profitability_authority"] = dict(authority)
            capital_admission = dict(opp.meta.get("capital_admission") or {})
            details = (
                dict(capital_admission.get("details") or {})
                if isinstance(capital_admission.get("details"), dict)
                else {}
            )
            details["terminalProfitabilityAuthority"] = dict(authority)
            details["terminalProfitability"] = dict(profitability)
            capital_admission["details"] = details
            opp.meta["capital_admission"] = capital_admission
            if capital_admission:
                plan.setdefault("capitalAdmission", dict(capital_admission))
        capital_admission_plan = (
            dict(plan.get("capitalAdmission") or {})
            if isinstance(plan.get("capitalAdmission"), dict)
            else {}
        )
        if capital_admission_plan:
            details = (
                dict(capital_admission_plan.get("details") or {})
                if isinstance(capital_admission_plan.get("details"), dict)
                else {}
            )
            details["terminalProfitabilityAuthority"] = dict(authority)
            details["terminalProfitability"] = dict(profitability)
            capital_admission_plan["details"] = details
            plan["capitalAdmission"] = capital_admission_plan

    def _execution_log_entry(
        self, runtime: Any, result: ExecResult, opp: Any, *, latency_ms: int, mode: str
    ) -> Dict[str, Any]:
        plan = dict(getattr(result, "plan", None) or {})
        return {
            "ts": int(time.time()),
            "chain": str(
                getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or ""
            ),
            "opportunity_id": str(getattr(opp, "id", "") or ""),
            "route_id": str(getattr(opp, "route_id", "") or plan.get("route_id") or ""),
            "mode": str(mode or "manual"),
            "latency_ms": int(latency_ms or 0),
            "ok": bool(getattr(result, "ok", False)),
            "dry_run": bool(getattr(result, "dry_run", False)),
            "attempted": bool(getattr(result, "attempted", False)),
            "submitted": bool(getattr(result, "submitted", False)),
            "reason": str(getattr(result, "reason", "") or ""),
            "tx_hash": str(getattr(result, "tx_hash", "") or ""),
            "plan": plan,
        }

    def _pnl_trade_row(
        self, runtime: Any, result: ExecResult, opp: Any, *, mode: str
    ) -> Dict[str, Any]:
        meta = (
            dict(getattr(opp, "meta", {}) or {})
            if isinstance(getattr(opp, "meta", None), dict)
            else {}
        )
        safety = dict(meta.get("safety") or {}) if isinstance(meta.get("safety"), dict) else {}
        plan = dict(getattr(result, "plan", None) or {})
        terminal_authority = dict(plan.get("terminalProfitabilityAuthority") or {})
        terminal_profitability = (
            dict(terminal_authority.get("profitability") or {})
            if isinstance(terminal_authority.get("profitability"), dict)
            else {}
        )
        plan_profitability = dict(plan.get("profitability") or {})
        return {
            "ts": int(time.time()),
            "chain": str(
                getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or ""
            ),
            "opportunity_id": str(getattr(opp, "id", "") or ""),
            "route_id": str(getattr(opp, "route_id", "") or plan.get("route_id") or ""),
            "tx_hash": str(getattr(result, "tx_hash", "") or ""),
            "mode": str(mode or "manual"),
            "dry_run": bool(getattr(result, "dry_run", False)),
            "ok": bool(getattr(result, "ok", False)),
            "reason": str(getattr(result, "reason", "") or ""),
            "expected_gross_profit_wei": str(
                terminal_profitability.get("gross_profit_wei")
                or plan_profitability.get("gross_profit_wei")
                or getattr(opp, "expected_profit_raw", "0")
                or "0"
            ),
            "expected_profit_after_costs_wei": str(
                terminal_profitability.get("profit_after_costs_wei")
                or plan_profitability.get("profit_after_costs_wei")
                or plan.get("profit_after_costs")
                or safety.get("profit_after_costs_wei")
                or getattr(opp, "expected_profit_raw", "0")
                or "0"
            ),
            "estimated_gas_cost_wei": str(
                terminal_profitability.get("gas_cost_wei")
                or plan_profitability.get("gas_cost_wei")
                or plan.get("gas_cost")
                or safety.get("gas_cost_wei")
                or "0"
            ),
            "flashloan_fee_wei": str(
                terminal_profitability.get("flashloan_fee_wei")
                or plan_profitability.get("flashloan_fee_wei")
                or plan.get("flashloan_fee")
                or safety.get("flashloan_fee_wei")
                or "0"
            ),
        }

    def _record_failure(self, runtime: Any, *, code: str) -> str:
        failure = str(code or "record_exec_failed")
        try:
            errors = getattr(runtime, "_errors", None)
            if errors is not None and hasattr(errors, "append"):
                errors.append(failure)
        except _RECORDING_FAILURES:
            pass
        return failure

    def _create_replay_bundle_for_record(
        self, runtime: Any, result: ExecResult, opp: Any, *, latency_ms: int, mode: str
    ) -> str:
        creator = getattr(runtime, "_create_replay_bundle", None)
        if creator is None or not callable(creator):
            return ""
        try:
            plan = dict(getattr(result, "plan", None) or {})
            return str(
                creator(
                    opportunity_id=str(getattr(opp, "id", "") or ""),
                    route_id=str(getattr(opp, "route_id", "") or plan.get("route_id") or ""),
                    mode=str(mode or "manual"),
                    rl_state="",
                    rl_action=-1,
                    latency_ms=int(latency_ms or 0),
                    plan=plan,
                    dry_run=bool(getattr(result, "dry_run", False)),
                    ok=bool(getattr(result, "ok", False)),
                    attempted=bool(getattr(result, "attempted", False)),
                    submitted=bool(getattr(result, "submitted", False)),
                    reason=str(getattr(result, "reason", "") or ""),
                    tx_hash=str(getattr(result, "tx_hash", "") or ""),
                    block_number=int(plan.get("current_block") or 0),
                    status=(
                        "dry_run"
                        if bool(getattr(result, "dry_run", False))
                        else (
                            "submitted"
                            if bool(getattr(result, "submitted", False))
                            else ("failed" if not bool(getattr(result, "ok", False)) else "draft")
                        )
                    ),
                )
            )
        except _SAFE_RUNTIME_EXCEPTIONS:
            return ""

    def _build_pending_submission(
        self, runtime: Any, result: ExecResult, opp: Any, *, latency_ms: int, mode: str
    ) -> Dict[str, Any]:
        plan = dict(getattr(result, "plan", None) or {})
        meta = (
            dict(getattr(opp, "meta", {}) or {})
            if isinstance(getattr(opp, "meta", None), dict)
            else {}
        )
        brain = dict(meta.get("brain") or {}) if isinstance(meta.get("brain"), dict) else {}
        capture_meta = (
            dict(meta.get("capture") or {}) if isinstance(meta.get("capture"), dict) else {}
        )
        capture_metadata = (
            dict(capture_meta.get("metadata") or {})
            if isinstance(capture_meta.get("metadata"), dict)
            else {}
        )
        envelope = (
            dict(capture_metadata.get("envelope") or {})
            if isinstance(capture_metadata.get("envelope"), dict)
            else {}
        )
        endpoint = (
            dict(capture_metadata.get("endpoint_selection") or {})
            if isinstance(capture_metadata.get("endpoint_selection"), dict)
            else {}
        )
        terminal_authority = (
            dict(plan.get("terminalProfitabilityAuthority") or {})
            if isinstance(plan.get("terminalProfitabilityAuthority"), dict)
            else {}
        )
        capital_admission = (
            dict(plan.get("capitalAdmission") or {})
            if isinstance(plan.get("capitalAdmission"), dict)
            else dict(meta.get("capital_admission") or {})
        )
        post_mutation_revalidation = (
            dict(plan.get("postMutationRevalidation") or {})
            if isinstance(plan.get("postMutationRevalidation"), dict)
            else dict(meta.get("post_mutation_revalidation") or {})
        )
        terminal_profitability = (
            dict(terminal_authority.get("profitability") or {})
            if isinstance(terminal_authority.get("profitability"), dict)
            else {}
        )
        post_mutation_profitability = (
            dict(post_mutation_revalidation.get("profitability") or {})
            if isinstance(post_mutation_revalidation.get("profitability"), dict)
            else {}
        )
        amount_in = str(
            plan.get("amount_in")
            or getattr(getattr(getattr(opp, "route", None), "legs", [None])[0], "amount_in", "0")
            or "0"
        )
        gas_est_wei = int(
            _safe_int(
                plan.get("gas_cost")
                or capture_metadata.get("gas_cost_wei")
                or ((meta.get("safety") or {}) if isinstance(meta.get("safety"), dict) else {}).get(
                    "gas_cost_wei"
                )
                or 0
            )
        )
        return {
            "tx_hash": str(getattr(result, "tx_hash", "") or ""),
            "submit_ts_s": int(time.time()),
            "expected_after": str(
                terminal_profitability.get("profit_after_costs_wei")
                or post_mutation_profitability.get("profit_after_costs_wei")
                or plan.get("profit_after_costs")
                or ((meta.get("safety") or {}) if isinstance(meta.get("safety"), dict) else {}).get(
                    "profit_after_costs_wei"
                )
                or getattr(opp, "expected_profit_raw", "0")
                or "0"
            ),
            "amount_in": amount_in,
            "latency_ms": int(latency_ms or 0),
            "mode": str(mode or "manual"),
            "route_id": str(getattr(opp, "route_id", "") or plan.get("route_id") or ""),
            "rl_state": str(brain.get("state") or brain.get("rl_state") or ""),
            "rl_action": int(brain.get("action_index") or brain.get("rl_action_index") or -1),
            "aqe_action": str(brain.get("aqe_action") or ""),
            "gas_est_wei": int(gas_est_wei),
            "capture_lane": str(capture_meta.get("lane") or meta.get("execution_lane") or ""),
            "capture_relay": str(capture_meta.get("relay_hint") or endpoint.get("relay") or ""),
            "capture_meta": capture_meta,
            "route_family": str(envelope.get("route_family") or meta.get("route_family") or ""),
            "strategy_family": str(meta.get("strategy_family") or "flashloan_atomic"),
            "pending_context": (
                dict(meta.get("pending_context") or {})
                if isinstance(meta.get("pending_context"), dict)
                else {}
            ),
            "tokens": [],
            "venues": [],
            "pairs": [],
            "terminal_profitability_authority": terminal_authority,
            "capital_admission": capital_admission,
            "post_mutation_revalidation": post_mutation_revalidation,
        }

    async def record_execution(
        self, runtime: Any, result: ExecResult, opp: Any, *, latency_ms: int, mode: str
    ) -> Dict[str, Any]:
        exec_log_entry = self._execution_log_entry(
            runtime, result, opp, latency_ms=latency_ms, mode=mode
        )
        pnl_row = self._pnl_trade_row(runtime, result, opp, mode=mode)
        try:
            runtime._exec_log.append(dict(exec_log_entry))
        except _RECORDING_FAILURES:
            self._record_failure(runtime, code="record_exec:exec_log_append_failed")
        try:
            if bool(getattr(result, "attempted", False)) or bool(
                getattr(result, "submitted", False)
            ):
                runtime.metrics.attempted += 1
        except _SAFE_RUNTIME_EXCEPTIONS:
            pass
        try:
            pnl = getattr(runtime, "_pnl", None)
            if pnl is not None and hasattr(pnl, "add_trade"):
                await pnl.add_trade(dict(pnl_row))
        except _SAFE_RUNTIME_EXCEPTIONS:
            self._record_failure(runtime, code="record_exec:pnl_add_trade_failed")
        replay_event_id = self._create_replay_bundle_for_record(
            runtime, result, opp, latency_ms=latency_ms, mode=mode
        )
        try:
            if replay_event_id and runtime._exec_log:
                runtime._exec_log[-1]["replay_event_id"] = str(replay_event_id)
        except _RECORDING_FAILURES:
            self._record_failure(runtime, code="record_exec:exec_log_replay_link_failed")
        tx_hash = str(getattr(result, "tx_hash", "") or "")
        if (
            bool(getattr(result, "submitted", False))
            and bool(getattr(result, "ok", False))
            and (not bool(getattr(result, "dry_run", False)))
            and tx_hash
        ):
            pending = self._build_pending_submission(
                runtime, result, opp, latency_ms=latency_ms, mode=mode
            )
            try:
                runtime._pending[tx_hash] = dict(pending)
                runtime._pending_gas_est_wei += int(_safe_int(pending.get("gas_est_wei") or 0))
            except _RECORDING_FAILURES:
                self._record_failure(runtime, code="record_exec:pending_store_failed")
            else:
                try:
                    runtime._receipt_q.put_nowait(tx_hash)
                except _PENDING_QUEUE_FAILURES:
                    pass
        return {"ok": True}

    def scale_opportunity(self, opp: Any, size_mult: float) -> Any:
        """Conservatively scale down an opportunity (no re-quote)."""
        sm = float(size_mult)
        if sm >= 1.0 or sm <= 0.0:
            return opp
        o2 = opp.model_copy(deep=True)
        try:
            amount_in0 = int(o2.route.legs[0].amount_in)
        except (AttributeError, KeyError, TypeError, ValueError):
            return o2
        new_in0 = max(1, int(amount_in0 * sm))
        try:
            o2.route.legs[0].amount_in = str(new_in0)
            o2.route.legs[0].min_out = str(max(0, int(int(o2.route.legs[0].min_out) * sm)))
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        try:
            if isinstance(o2.meta, dict) and "out1" in o2.meta:
                out1 = int(str(o2.meta.get("out1") or "0"))
                o2.meta["out1"] = str(max(0, int(out1 * sm)))
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        try:
            if len(o2.route.legs) > 1:
                try:
                    out1_scaled = int(str(o2.meta.get("out1") or "0"))
                except (AttributeError, KeyError, TypeError, ValueError):
                    out1_scaled = max(0, int(int(o2.route.legs[1].amount_in) * sm))
                o2.route.legs[1].amount_in = str(out1_scaled)
                o2.route.legs[1].min_out = str(max(0, int(int(o2.route.legs[1].min_out) * sm)))
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        _sync_scaled_profit_fields(o2, sm)
        try:
            o2.min_outs = [str(max(0, int(int(x) * sm))) for x in (o2.min_outs or [])]
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        if isinstance(o2.meta, dict):
            o2.meta.setdefault("brain", {})
            o2.meta["brain"].setdefault("size_mult_applied", sm)
        return o2

    def resolve_amount_in(self, runtime: Any) -> int:
        ctx = build_execution_runtime_signals(runtime)
        base = int(ctx.base_borrow_amount)
        if base <= 0:
            for amount_in in ctx.route_amount_candidates:
                if amount_in > 0:
                    base = int(amount_in)
                    break
        runtime._bankroll.cfg.base_borrow_amount_wei = base
        if ctx.controls is not None:
            runtime._bankroll.apply_overrides(
                kelly_enabled=bool(getattr(ctx.controls, "kelly_enabled", False)),
                auto_reinvest_enabled=bool(getattr(ctx.controls, "auto_reinvest_enabled", False)),
            )
        return runtime._bankroll.next_amount_in()

    def as_outcome(self, result: ExecResult) -> ExecutionOutcome:
        status = (
            "accepted"
            if bool(result.ok)
            else ("failed" if bool(result.attempted or result.submitted) else "dropped")
        )
        return ExecutionOutcome(
            status=status,
            reason_code=str(result.reason or "unknown"),
            retryable=bool(not result.ok and not result.submitted),
            degraded_mode="",
            tx_hash=str(result.tx_hash or ""),
            details=dict(result.plan or {}),
        )

    def build_live_state(self, runtime: Any) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        try:
            pending_items = list(getattr(runtime, "_pending", {}).items())
            pending_items.sort(
                key=lambda kv: int(
                    (kv[1] or {}).get("created_at_ms") or (kv[1] or {}).get("ts_ms") or 0
                )
            )
            for tx_hash, pending in pending_items[-12:]:
                if not isinstance(pending, dict):
                    continue
                capture_meta = dict(pending.get("capture_meta") or {})
                meta = dict(capture_meta.get("metadata") or {})
                endpoint = dict(meta.get("endpoint_selection") or {})
                route_plan = dict(meta.get("route_plan") or {})
                exec_plan = dict(meta.get("execution_route_plan") or {})
                adv = dict(meta.get("adversarial_state") or {})
                flash = dict(meta.get("flashloan_resilience") or {})
                pending_context = dict(
                    pending.get("pending_context") or meta.get("pending_context") or {}
                )
                capital_admission = dict(pending.get("capital_admission") or {})
                if capital_admission:
                    capital_admission["stateContract"] = contract_from_surface(
                        capital_admission,
                        phase="capital_admission",
                        default_reason=str(
                            capital_admission.get("reason_code")
                            or capital_admission.get("reason")
                            or (
                                "ok"
                                if capital_admission.get(
                                    "allowed", capital_admission.get("ok", True)
                                )
                                else "denied"
                            )
                        ),
                        sticky_cycle=True,
                        details={
                            "capitalSource": str(capital_admission.get("capital_source") or ""),
                            "requestedNotionalUsd": float(
                                capital_admission.get("requested_notional_usd") or 0.0
                            ),
                        },
                    )
                family_info = _canonical_family_identity(
                    pending.get("strategy_family") or pending.get("route_family") or "flashloan_atomic"
                )
                items.append(
                    {
                        "txHash": str(tx_hash or ""),
                        "routeFamily": str(pending.get("route_family") or ""),
                        "family": str(family_info.get("launchFamily") or ""),
                        "requestedFamily": str(family_info.get("requestedFamily") or ""),
                        "runtimeFamily": str(family_info.get("runtimeFamily") or ""),
                        "capitalFamily": str(family_info.get("capitalFamily") or ""),
                        "displayFamily": str(family_info.get("displayName") or ""),
                        "familyAliases": list(family_info.get("aliases") or []),
                        "lane": str(capture_meta.get("lane") or ""),
                        "endpoint": str(
                            capture_meta.get("endpoint_hint") or endpoint.get("endpoint") or ""
                        ),
                        "relay": str(capture_meta.get("relay_hint") or endpoint.get("relay") or ""),
                        "endpointReason": str(
                            endpoint.get("reason") or endpoint.get("pressure_class") or ""
                        ),
                        "endpointUniverseReason": str(
                            (
                                (endpoint.get("universe") or {})
                                if isinstance(endpoint.get("universe"), dict)
                                else {}
                            ).get("reason")
                            or ""
                        ),
                        "selectedVenues": list(
                            exec_plan.get("selected_venues")
                            or route_plan.get("selected_venues")
                            or []
                        ),
                        "fallbackReady": bool(
                            exec_plan.get("fallback_tree") or route_plan.get("fallback_tree")
                        ),
                        "routeExecutable": bool(exec_plan.get("executable", True)),
                        "routeInvalidCauses": list(
                            exec_plan.get("route_invalid_causes")
                            or meta.get("route_invalid_causes")
                            or []
                        ),
                        "adversarial": {
                            "pendingCount": (
                                int((pending_context.get("summary") or {}).get("count") or 0)
                                if isinstance(pending_context, dict)
                                else 0
                            ),
                            "staleProbability": float(adv.get("stale_probability") or 0.0),
                            "interferenceProbability": float(
                                adv.get("interference_probability") or 0.0
                            ),
                            "postOrderingRealizedEdge": float(
                                adv.get("post_ordering_realized_edge") or 0.0
                            ),
                            "copyRisk": float(adv.get("copy_risk") or 0.0),
                            "relayNecessity": float(adv.get("relay_necessity") or 0.0),
                            "requiresPrivateLane": bool(adv.get("requires_private_lane")),
                        },
                        "flashloan": {
                            "providerPriority": list(flash.get("provider_priority") or []),
                            "selectedProvider": str(flash.get("selected_provider") or ""),
                            "fallbackProvider": str(flash.get("fallback_provider") or ""),
                            "reserveDistortion": float(flash.get("reserve_distortion") or 0.0),
                            "routeViable": bool(flash.get("route_viable", True)),
                            "searcherInvalidation": bool(flash.get("searcher_invalidation", False)),
                            "reasonCodes": list(flash.get("reason_codes") or []),
                            "routeMutationRequired": bool(
                                flash.get("route_mutation_required", False)
                            ),
                            "flashloanFeeWei": int(
                                pending.get("flashloan_fee_wei")
                                or flash.get("flashloan_fee_wei")
                                or 0
                            ),
                            "borrowCostUsd": float(
                                pending.get("borrow_cost_usd")
                                or (
                                    (flash.get("sizing") or {})
                                    if isinstance(flash.get("sizing"), dict)
                                    else {}
                                ).get("borrowCostUsd")
                                or (
                                    (flash.get("sizing") or {})
                                    if isinstance(flash.get("sizing"), dict)
                                    else {}
                                ).get("borrow_cost_usd")
                                or 0.0
                            ),
                            "sizing": dict(
                                (flash.get("sizing") or {})
                                if isinstance(flash.get("sizing"), dict)
                                else {}
                            ),
                            "providerChoiceReason": str(
                                (
                                    (
                                        (flash.get("sizing") or {})
                                        if isinstance(flash.get("sizing"), dict)
                                        else {}
                                    ).get("provider_choice_reason")
                                )
                                or ""
                            ),
                        },
                        "terminalProfitabilityAuthority": dict(
                            pending.get("terminal_profitability_authority") or {}
                        ),
                        "capitalAdmission": capital_admission,
                        "postMutationRevalidation": dict(
                            pending.get("post_mutation_revalidation") or {}
                        ),
                        "tsMs": int(pending.get("created_at_ms") or pending.get("ts_ms") or 0),
                    }
                )
        except (AttributeError, KeyError, TypeError, ValueError):
            return {"items": []}
        return {"items": items[-5:]}

    def summarize(self, runtime: Any) -> Dict[str, Any]:
        live = self.build_live_state(runtime)
        items = list((live.get("items") or [])) if isinstance(live, dict) else []
        latest = items[-1] if items else {}
        flash = dict(latest.get("flashloan") or {}) if isinstance(latest, dict) else {}
        sizing = dict(flash.get("sizing") or {}) if isinstance(flash, dict) else {}
        capital_admission = (
            dict(latest.get("capitalAdmission") or {}) if isinstance(latest, dict) else {}
        )
        if capital_admission:
            capital_admission["stateContract"] = contract_from_surface(
                capital_admission,
                phase="capital_admission",
                default_reason=str(
                    capital_admission.get("reason_code") or capital_admission.get("reason") or "ok"
                ),
                sticky_cycle=True,
                details={
                    "capitalSource": str(capital_admission.get("capital_source") or ""),
                    "requestedNotionalUsd": float(
                        capital_admission.get("requested_notional_usd") or 0.0
                    ),
                },
            )
        post_mutation_revalidation = (
            dict(latest.get("postMutationRevalidation") or {}) if isinstance(latest, dict) else {}
        )
        route_executable = bool(latest.get("routeExecutable", True)) if items else True
        fallback_ready = bool(latest.get("fallbackReady", False)) if items else True
        route_invalid_causes = list(latest.get("routeInvalidCauses") or []) if items else []
        reason_code = "idle" if not items else "ok"
        blocked = False
        degraded = False
        if (
            items
            and capital_admission
            and not bool(capital_admission.get("allowed", capital_admission.get("ok", True)))
        ):
            reason_code = f"capital_admission:{str(capital_admission.get('reason_code') or capital_admission.get('reason') or 'denied')}"
            blocked = True
            degraded = True
        elif items and not route_executable:
            reason_code = str(
                route_invalid_causes[0] if route_invalid_causes else "route_not_executable"
            )
            degraded = True
        elif items and not fallback_ready:
            reason_code = "fallback_not_ready"
            degraded = True
        payload = {
            "ok": True,
            "lastEndpoint": str(latest.get("endpoint") or ""),
            "lastRouteFamily": str(latest.get("routeFamily") or ""),
            "lastFamily": str(latest.get("family") or ""),
            "lastRuntimeFamily": str(latest.get("runtimeFamily") or ""),
            "lastCapitalFamily": str(latest.get("capitalFamily") or ""),
            "lastDisplayFamily": str(latest.get("displayFamily") or ""),
            "lastFamilyAliases": list(latest.get("familyAliases") or []),
            "lastFamilyIdentity": (
                family_identity(str(latest.get("runtimeFamily") or latest.get("family") or "flashloan_atomic"))
                if isinstance(latest, dict)
                else family_identity("flashloan_atomic")
            ),
            "lastTerminalProfitabilityAuthority": (
                dict(latest.get("terminalProfitabilityAuthority") or {})
                if isinstance(latest, dict)
                else {}
            ),
            "lastCapitalAdmission": capital_admission,
            "lastPostMutationRevalidation": post_mutation_revalidation,
            "lastLane": str(latest.get("lane") or ""),
            "lastRelay": str(latest.get("relay") or ""),
            "lastProvider": str(flash.get("selectedProvider") or ""),
            "lastFlashloanFeeWei": int(flash.get("flashloanFeeWei") or 0),
            "lastBorrowCostUsd": float(flash.get("borrowCostUsd") or 0.0),
            "lastSizeMult": float(sizing.get("size_mult") or latest.get("sizeMult") or 1.0),
            "lastBorrowMult": float(sizing.get("borrow_mult") or 1.0),
            "providerChoiceReason": str(
                flash.get("providerChoiceReason") or sizing.get("provider_choice_reason") or ""
            ),
            "routeExecutable": route_executable,
            "fallbackReady": fallback_ready,
            "routeInvalidCauses": route_invalid_causes,
        }
        return attach_state_contract(
            payload,
            phase="execution",
            reason_code=reason_code,
            degraded=degraded,
            blocked=blocked,
            sticky_cycle=True,
            details={
                "lastEndpoint": str(latest.get("endpoint") or ""),
                "lastLane": str(latest.get("lane") or ""),
            },
        )
