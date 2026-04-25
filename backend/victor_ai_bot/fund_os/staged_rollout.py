from __future__ import annotations

import time
from typing import Any, Dict, List

from ..domain_errors import InvalidTransitionError
from ..persistence.db import PersistenceDB
from ..persistence.repositories.launch_repository import LaunchRepository
from .activation_readiness import (
    activation_decision,
    blocked_readiness_codes,
    primary_readiness_reason,
)
from .capability_health_graph import CapabilityHealthGraph
from .family_identity import canonical_launch_family_id, is_core_launch_family
from .family_readiness import build_family_readiness
from .health_states import HealthState, normalize_health_state
from .launch_acceleration import build_launch_acceleration_summary
from .launch_modes import DEFAULT_ACTIVATION_ORDER, LaunchMode, LaunchProfile
from .state_transitions import append_transition, apply_transition


def _unique_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        value_s = str(value or "")
        if value_s and value_s not in out:
            out.append(value_s)
    return out


def _blocked_detail_reason_codes(detail: Dict[str, Any]) -> list[str]:
    return _unique_strings(
        [
            str(detail.get("reason_code") or ""),
            *[str(x) for x in list(detail.get("blocked_by") or []) if str(x)],
            *[str(x) for x in list(detail.get("global_execution_reason_codes") or []) if str(x)],
            *[
                str(x)
                for x in list(detail.get("receipt_outcome_truth_reason_codes") or [])
                if str(x)
            ],
            *[str(x) for x in list(detail.get("capital_truth_reason_codes") or []) if str(x)],
            *[str(x) for x in list(detail.get("internal_prime_reason_codes") or []) if str(x)],
            *[str(x) for x in list(detail.get("launch_acceleration_reason_codes") or []) if str(x)],
            *[str(x) for x in list(detail.get("launch_acceleration_stability_reason_codes") or []) if str(x)],
        ]
    )


def _launch_hold_summary(
    *, blocked_details: Dict[str, Dict[str, Any]], recommended_next_family: str
) -> Dict[str, Any]:
    global_execution_reason_codes = _unique_strings(
        [
            str(code)
            for detail in blocked_details.values()
            for code in list(detail.get("global_execution_reason_codes") or [])
            if str(code)
        ]
    )
    capital_truth_reason_codes = _unique_strings(
        [
            str(code)
            for detail in blocked_details.values()
            for code in list(detail.get("capital_truth_reason_codes") or [])
            if str(code)
        ]
    )
    receipt_outcome_truth_reason_codes = _unique_strings(
        [
            str(code)
            for detail in blocked_details.values()
            for code in list(detail.get("receipt_outcome_truth_reason_codes") or [])
            if str(code)
        ]
    )
    internal_prime_reason_codes = _unique_strings(
        [
            str(code)
            for detail in blocked_details.values()
            for code in list(detail.get("internal_prime_reason_codes") or [])
            if str(code)
        ]
    )
    hold_reason_codes = _unique_strings(
        [
            *global_execution_reason_codes,
            *receipt_outcome_truth_reason_codes,
            *capital_truth_reason_codes,
            *internal_prime_reason_codes,
            *[
                code
                for detail in blocked_details.values()
                for code in _blocked_detail_reason_codes(detail)
            ],
        ]
    )
    hold_reason_code = (
        hold_reason_codes[0] if hold_reason_codes and not recommended_next_family else ""
    )
    suggested_next_action = ""
    if hold_reason_code and not recommended_next_family:
        for detail in blocked_details.values():
            if hold_reason_code in _blocked_detail_reason_codes(detail):
                suggested_next_action = str(
                    detail.get("recovery_next_action") or detail.get("suggested_next_action") or ""
                )
                if suggested_next_action:
                    break
        if not suggested_next_action and blocked_details:
            first = next(iter(blocked_details.values()))
            suggested_next_action = str(
                first.get("recovery_next_action")
                or first.get("suggested_next_action")
                or "continue_v1_learning"
            )

    recovery_reason_codes = _unique_strings(
        [
            str(code)
            for detail in blocked_details.values()
            for code in list(detail.get("recovery_reason_codes") or [])
            if str(code)
        ]
    )
    if not recovery_reason_codes:
        recovery_reason_codes = _unique_strings(
            [
                *global_execution_reason_codes,
                *internal_prime_reason_codes,
                *receipt_outcome_truth_reason_codes,
                *capital_truth_reason_codes,
            ]
        )
    recovery_status = "ready"
    recovery_reason_code = "ok"
    recovery_next_action = ""
    recovery_ready = True
    recovery_freshness_class = "current"
    recovery_freshness_reason_code = "ok"
    recovery_freshness_reason_codes: list[str] = []
    recovery_freshness_next_action = ""
    recovery_history_component = ""
    recovery_history_status = "steady"
    recovery_degraded_since_ts_ms = 0
    recovery_recovered_at_ts_ms = 0
    recovery_degraded_duration_ms = 0
    recovery_degraded_count = 0
    recovery_last_healthy_ts_ms = 0
    recovery_recovered_recently = False
    recovery_degradation_severity_class = "stable"
    recovery_reliability_class = "stable"
    recovery_reliability_reason_code = "ok"
    recovery_reliability_reason_codes: list[str] = []
    recovery_reliability_next_action = ""
    recovery_recovered_fragile = False
    if recovery_reason_codes and not recommended_next_family:
        recovery_ready = False
        recovery_reason_code = recovery_reason_codes[0]
        recovery_status = (
            "global_execution_blocked"
            if global_execution_reason_codes
            else (
                "internal_prime_reconciliation_required"
                if internal_prime_reason_codes
                else "capital_truth_restore_required"
            )
        )
        for detail in blocked_details.values():
            detail_recovery_codes = _unique_strings(
                [str(x) for x in list(detail.get("recovery_reason_codes") or []) if str(x)]
            )
            if (
                recovery_reason_code in detail_recovery_codes
                or recovery_reason_code in _blocked_detail_reason_codes(detail)
            ):
                recovery_next_action = str(
                    detail.get("recovery_next_action") or detail.get("suggested_next_action") or ""
                )
                if recovery_next_action:
                    break
        if not recovery_next_action and blocked_details:
            first = next(iter(blocked_details.values()))
            recovery_next_action = str(
                first.get("recovery_next_action")
                or first.get("suggested_next_action")
                or "continue_v1_learning"
            )
        for detail in blocked_details.values():
            detail_recovery_codes = _unique_strings(
                [str(x) for x in list(detail.get("recovery_reason_codes") or []) if str(x)]
            )
            if (
                recovery_reason_code in detail_recovery_codes
                or recovery_reason_code in _blocked_detail_reason_codes(detail)
            ):
                recovery_freshness_class = str(detail.get("recovery_freshness_class") or "unknown")
                recovery_freshness_reason_code = str(
                    detail.get("recovery_freshness_reason_code") or "ok"
                )
                recovery_freshness_reason_codes = _unique_strings(
                    [
                        str(x)
                        for x in list(detail.get("recovery_freshness_reason_codes") or [])
                        if str(x)
                    ]
                )
                recovery_freshness_next_action = str(
                    detail.get("recovery_freshness_next_action") or ""
                )
                recovery_history_component = str(detail.get("recovery_history_component") or "")
                recovery_history_status = str(detail.get("recovery_history_status") or "steady")
                recovery_degraded_since_ts_ms = int(
                    detail.get("recovery_degraded_since_ts_ms") or 0
                )
                recovery_recovered_at_ts_ms = int(detail.get("recovery_recovered_at_ts_ms") or 0)
                recovery_degraded_duration_ms = int(
                    detail.get("recovery_degraded_duration_ms") or 0
                )
                recovery_degraded_count = int(detail.get("recovery_degraded_count") or 0)
                recovery_last_healthy_ts_ms = int(detail.get("recovery_last_healthy_ts_ms") or 0)
                recovery_recovered_recently = bool(detail.get("recovery_recovered_recently", False))
                recovery_degradation_severity_class = str(
                    detail.get("recovery_degradation_severity_class") or "stable"
                )
                recovery_reliability_class = str(
                    detail.get("recovery_reliability_class") or "stable"
                )
                recovery_reliability_reason_code = str(
                    detail.get("recovery_reliability_reason_code") or "ok"
                )
                recovery_reliability_reason_codes = _unique_strings(
                    [
                        str(x)
                        for x in list(detail.get("recovery_reliability_reason_codes") or [])
                        if str(x)
                    ]
                )
                recovery_reliability_next_action = str(
                    detail.get("recovery_reliability_next_action")
                    or detail.get("recovery_next_action")
                    or ""
                )
                recovery_recovered_fragile = bool(detail.get("recovery_recovered_fragile", False))
                break
        if (
            recovery_freshness_reason_code != "ok"
            and recovery_freshness_reason_code not in recovery_freshness_reason_codes
        ):
            recovery_freshness_reason_codes = [
                recovery_freshness_reason_code,
                *recovery_freshness_reason_codes,
            ]

    return {
        "global_execution_blocked": bool(global_execution_reason_codes),
        "global_execution_reason_codes": global_execution_reason_codes,
        "capital_truth_reason_codes": capital_truth_reason_codes,
        "receipt_outcome_truth_reason_codes": receipt_outcome_truth_reason_codes,
        "internal_prime_reason_codes": internal_prime_reason_codes,
        "hold_reason_code": hold_reason_code,
        "hold_reason_codes": hold_reason_codes if not recommended_next_family else [],
        "suggested_next_action": suggested_next_action if not recommended_next_family else "",
        "recovery_ready": recovery_ready if not recommended_next_family else True,
        "recovery_status": recovery_status if not recommended_next_family else "ready",
        "recovery_reason_code": recovery_reason_code if not recommended_next_family else "ok",
        "recovery_reason_codes": recovery_reason_codes if not recommended_next_family else [],
        "recovery_next_action": recovery_next_action if not recommended_next_family else "",
        "recovery_freshness_class": (
            recovery_freshness_class if not recommended_next_family else "current"
        ),
        "recovery_freshness_reason_code": (
            recovery_freshness_reason_code if not recommended_next_family else "ok"
        ),
        "recovery_freshness_reason_codes": (
            recovery_freshness_reason_codes if not recommended_next_family else []
        ),
        "recovery_freshness_next_action": (
            recovery_freshness_next_action if not recommended_next_family else ""
        ),
        "recovery_history_component": (
            recovery_history_component if not recommended_next_family else ""
        ),
        "recovery_history_status": (
            recovery_history_status if not recommended_next_family else "steady"
        ),
        "recovery_degraded_since_ts_ms": (
            recovery_degraded_since_ts_ms if not recommended_next_family else 0
        ),
        "recovery_recovered_at_ts_ms": (
            recovery_recovered_at_ts_ms if not recommended_next_family else 0
        ),
        "recovery_degraded_duration_ms": (
            recovery_degraded_duration_ms if not recommended_next_family else 0
        ),
        "recovery_degraded_count": recovery_degraded_count if not recommended_next_family else 0,
        "recovery_last_healthy_ts_ms": (
            recovery_last_healthy_ts_ms if not recommended_next_family else 0
        ),
        "recovery_recovered_recently": (
            recovery_recovered_recently if not recommended_next_family else False
        ),
        "recovery_degradation_severity_class": (
            recovery_degradation_severity_class if not recommended_next_family else "stable"
        ),
        "recovery_reliability_class": (
            recovery_reliability_class if not recommended_next_family else "stable"
        ),
        "recovery_reliability_reason_code": (
            recovery_reliability_reason_code if not recommended_next_family else "ok"
        ),
        "recovery_reliability_reason_codes": (
            recovery_reliability_reason_codes if not recommended_next_family else []
        ),
        "recovery_reliability_next_action": (
            recovery_reliability_next_action if not recommended_next_family else ""
        ),
        "recovery_recovered_fragile": (
            recovery_recovered_fragile if not recommended_next_family else False
        ),
    }


class StagedRolloutManager:
    def __init__(self, *, data_dir: str, chain: str):
        self._repo = LaunchRepository(
            PersistenceDB(f"{data_dir}/state/xdv_runtime_state.sqlite3"),
            chain=chain,
            path=f"{data_dir}/fund_os/launch_state_{chain}.json",
        )
        raw = self._repo.load() or {}
        self.profile = LaunchProfile(
            **({k: raw[k] for k in LaunchProfile.__annotations__.keys() if k in raw} or {})
        )
        self._normalize_profile()
        if not self.profile.updated_ts_ms:
            self._touch("bootstrap")

    def _normalize_profile(self) -> None:
        for family in DEFAULT_ACTIVATION_ORDER:
            if family not in self.profile.family_states:
                self.profile.family_states[family] = (
                    HealthState.LIVE.value
                    if family == "flash_arb"
                    else HealthState.OBSERVE_ONLY.value
                )
            else:
                self.profile.family_states[family] = normalize_health_state(
                    self.profile.family_states.get(family),
                    default=(
                        HealthState.LIVE.value
                        if family == "flash_arb"
                        else HealthState.OBSERVE_ONLY.value
                    ),
                )
        if "flash_arb" not in self.profile.active_families:
            self.profile.active_families.insert(0, "flash_arb")
        self.profile.active_families = [
            f for f in self.profile.active_families if f in DEFAULT_ACTIVATION_ORDER
        ]
        if self.profile.mode == LaunchMode.V1_ONLY.value:
            self.profile.active_families = ["flash_arb"]
            for family in DEFAULT_ACTIVATION_ORDER:
                if (
                    family != "flash_arb"
                    and self.profile.family_states.get(family) == HealthState.LIVE.value
                ):
                    self.profile.family_states[family] = HealthState.OBSERVE_ONLY.value

    def _touch(self, reason: str) -> None:
        self.profile.updated_ts_ms = int(time.time() * 1000)
        if reason:
            self.profile.history = append_transition(
                self.profile.history,
                {
                    "ts_ms": self.profile.updated_ts_ms,
                    "reason_code": reason,
                    "profile_mode": self.profile.mode,
                    "active_families": list(self.profile.active_families),
                },
            )
        self._repo.save(self.profile.to_dict())

    def _apply_family_state(
        self,
        family: str,
        target_state: str,
        *,
        actor: str,
        reason_code: str,
        details: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        current = self.profile.family_states.get(family, HealthState.OBSERVE_ONLY.value)
        transition = apply_transition(
            family=family,
            current_state=current,
            target_state=target_state,
            actor=actor,
            reason_code=reason_code,
            details=details,
        )
        self.profile.family_states[family] = transition["to_state"]
        self.profile.last_transition = transition
        self.profile.history = append_transition(self.profile.history, transition)
        return transition

    def set_mode(self, mode: str, *, actor: str = "operator") -> Dict[str, Any]:
        mode = str(mode or LaunchMode.V1_ONLY.value)
        if mode not in {x.value for x in LaunchMode}:
            mode = LaunchMode.V1_ONLY.value
        self.profile.mode = mode
        if mode == LaunchMode.V1_ONLY.value:
            self.profile.active_families = ["flash_arb"]
            for family in DEFAULT_ACTIVATION_ORDER:
                self.profile.family_states[family] = (
                    HealthState.LIVE.value
                    if family == "flash_arb"
                    else HealthState.OBSERVE_ONLY.value
                )
        elif mode == LaunchMode.V1_PLUS_STABLE_ALPHA.value:
            self.profile.active_families = ["flash_arb", "funding_arb"]
            self.profile.family_states["flash_arb"] = HealthState.LIVE.value
            self.profile.family_states["funding_arb"] = normalize_health_state(
                self.profile.family_states.get("funding_arb"), default=HealthState.CAPPED_LIVE.value
            )
        self._touch(f"mode_set:{mode}")
        return self.profile.to_dict()

    def _readiness_items(
        self,
        *,
        stage: str,
        scorecards: Dict[str, Any],
        engine_state: Dict[str, Any],
        telemetry: Dict[str, Any],
        calibration: Dict[str, Any],
        fund_summary: Dict[str, Any],
        capital_state: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        active = [canonical_launch_family_id(str(x or "")) for x in list(self.profile.active_families)]
        return [
            build_family_readiness(
                family=f,
                stage=stage,
                scorecards=scorecards,
                engine_state=engine_state,
                telemetry=telemetry,
                calibration=calibration,
                fund_summary=fund_summary,
                active_families=active,
                family_states=self.profile.family_states,
                exploration_budget=self.profile.exploration_budget,
                capital_state=capital_state,
            )
            for f in self.profile.rollout_order
        ]

    def _update_exploration_budget(
        self, *, cost_usd: float = 0.0, trade_increment: int = 0
    ) -> None:
        budget = dict(self.profile.exploration_budget or {})
        budget["used_trades"] = int(budget.get("used_trades", 0) or 0) + int(trade_increment)
        budget["used_cost_usd"] = round(
            float(budget.get("used_cost_usd", 0.0) or 0.0) + float(cost_usd), 6
        )
        self.profile.exploration_budget = budget

    def enable_family(
        self,
        family: str,
        *,
        stage: str,
        scorecards: Dict[str, Any],
        engine_state: Dict[str, Any],
        telemetry: Dict[str, Any],
        calibration: Dict[str, Any],
        fund_summary: Dict[str, Any],
        capital_state: Dict[str, Any] | None = None,
        actor: str = "operator",
    ) -> Dict[str, Any]:
        family = canonical_launch_family_id(str(family or ""))
        if self.profile.mode == LaunchMode.V1_ONLY.value and not is_core_launch_family(family):
            return {
                "ok": False,
                "reason_code": "launch_mode_v1_only",
                "profile": self.profile.to_dict(),
                "readiness": {
                    "family": family,
                    "ready": False,
                    "reasons": ["launch_mode_v1_only"],
                    "blockers": ["launch_mode_v1_only"],
                    "status": "blocked",
                },
            }
        budget = dict(self.profile.exploration_budget or {})
        if family not in self.profile.active_families and int(
            budget.get("used_trades", 0) or 0
        ) >= int(budget.get("max_trades", 3)):
            return {
                "ok": False,
                "reason_code": "exploration_budget_exhausted",
                "profile": self.profile.to_dict(),
                "readiness": {
                    "family": family,
                    "ready": False,
                    "reasons": ["exploration_budget_exhausted"],
                    "blockers": ["exploration_budget_exhausted"],
                    "status": "blocked",
                },
            }
        dec = activation_decision(
            family=family,
            stage=stage,
            scorecards=scorecards,
            engine_state=engine_state,
            telemetry=telemetry,
            calibration=calibration,
            fund_summary=fund_summary,
            active_families=list(self.profile.active_families),
            family_states=self.profile.family_states,
            exploration_budget=self.profile.exploration_budget,
            capital_state=capital_state,
        )
        if not dec["allowed"]:
            return {
                "ok": False,
                "reason_code": dec["reason_code"],
                "blocked_by": dec.get("blocked_by") or [],
                "suggested_next_action": dec.get("suggested_next_action") or "",
                "readiness": dec["readiness"],
                "profile": self.profile.to_dict(),
            }
        if family not in self.profile.active_families:
            self.profile.active_families.append(family)
        self.profile.requested_families = sorted(set(self.profile.requested_families + [family]))
        # Production posture: flash remains live; secondary families enter capped_live first unless already live.
        target = (
            HealthState.LIVE.value
            if family == "flash_arb"
            else (
                HealthState.CAPPED_LIVE.value
                if dec.get("degraded_mode") in {"", HealthState.OBSERVE_ONLY.value}
                else str(dec.get("degraded_mode") or HealthState.CAPPED_LIVE.value)
            )
        )
        try:
            self._apply_family_state(
                family, target, actor=actor, reason_code="family_enabled", details={"stage": stage}
            )
        except InvalidTransitionError:
            self._apply_family_state(
                family,
                HealthState.CAPPED_LIVE.value,
                actor=actor,
                reason_code="family_enabled_safe_fallback",
                details={"stage": stage},
            )
        if not is_core_launch_family(family):
            self._update_exploration_budget(trade_increment=1)
        self._touch(f"family_enabled:{family}")
        return {
            "ok": True,
            "profile": self.profile.to_dict(),
            "readiness": dec["readiness"],
            "transition": dict(self.profile.last_transition),
        }

    def pause_family(self, family: str, *, actor: str = "operator") -> Dict[str, Any]:
        family = canonical_launch_family_id(str(family or ""))
        if not is_core_launch_family(family):
            self.profile.active_families = [canonical_launch_family_id(f) for f in self.profile.active_families if canonical_launch_family_id(f) != family]
        transition = self._apply_family_state(
            family, HealthState.OBSERVE_ONLY.value, actor=actor, reason_code="family_paused"
        )
        self._touch(f"family_paused:{family}")
        return {"ok": True, "profile": self.profile.to_dict(), "transition": transition}

    def revert_family(self, family: str, *, actor: str = "operator") -> Dict[str, Any]:
        family = canonical_launch_family_id(str(family or ""))
        target = (
            HealthState.OBSERVE_ONLY.value
            if not is_core_launch_family(family)
            else HealthState.CAPPED_LIVE.value
        )
        transition = self._apply_family_state(
            family, target, actor=actor, reason_code="family_reverted"
        )
        if not is_core_launch_family(family):
            self.profile.active_families = [canonical_launch_family_id(f) for f in self.profile.active_families if canonical_launch_family_id(f) != family]
        self._touch(f"family_reverted:{family}")
        return {"ok": True, "profile": self.profile.to_dict(), "transition": transition}

    def quarantine_family(
        self, family: str, *, actor: str = "system", reason_code: str = "quarantined"
    ) -> Dict[str, Any]:
        family = canonical_launch_family_id(str(family or ""))
        if not is_core_launch_family(family):
            self.profile.active_families = [canonical_launch_family_id(f) for f in self.profile.active_families if canonical_launch_family_id(f) != family]
        transition = self._apply_family_state(
            family, HealthState.QUARANTINED.value, actor=actor, reason_code=reason_code
        )
        self._touch(f"family_quarantined:{family}")
        return {"ok": True, "profile": self.profile.to_dict(), "transition": transition}

    def family_detail(
        self,
        family: str,
        *,
        stage: str,
        scorecards: Dict[str, Any],
        engine_state: Dict[str, Any],
        telemetry: Dict[str, Any],
        calibration: Dict[str, Any],
        fund_summary: Dict[str, Any],
        capital_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        items = self._readiness_items(
            stage=stage,
            scorecards=scorecards,
            engine_state=engine_state,
            telemetry=telemetry,
            calibration=calibration,
            fund_summary=fund_summary,
            capital_state=capital_state,
        )
        family = canonical_launch_family_id(str(family or ""))
        item = next((x for x in items if canonical_launch_family_id(str(x.get("family") or "")) == family), None)
        return {
            "ok": bool(item),
            "family": family,
            "item": item or {},
            "profile": self.profile.to_dict(),
        }

    def recommendation(
        self,
        *,
        stage: str,
        scorecards: Dict[str, Any],
        engine_state: Dict[str, Any],
        telemetry: Dict[str, Any],
        calibration: Dict[str, Any],
        fund_summary: Dict[str, Any],
        capital_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        items = self._readiness_items(
            stage=stage,
            scorecards=scorecards,
            engine_state=engine_state,
            telemetry=telemetry,
            calibration=calibration,
            fund_summary=fund_summary,
            capital_state=capital_state,
        )
        active = [canonical_launch_family_id(str(x or "")) for x in list(self.profile.active_families)]
        locked = [i for i in items if not i["active"]]
        acceleration = build_launch_acceleration_summary(
            profile=self.profile.to_dict(), readiness_items=items
        )
        candidates = [
            i
            for i in locked
            if i["ready"]
            and i.get("status") in {"eligible", "degraded"}
            and bool(i.get("launchAccelerationSeedReady", False))
        ]
        candidates.sort(
            key=lambda x: (
                int(x["rolloutIndex"]),
                -int(x.get("count") or 0),
                -float(x["score"]),
            )
        )
        flash = next((i for i in items if i["family"] == "flash_arb"), None)
        recommended_next_family = candidates[0]["family"] if candidates else ""
        reasons: List[str] = []
        rollback_recommendation = ""
        if flash and (
            flash.get("status") in {"blocked", "quarantined"}
            or float(flash.get("competitionPressure") or 0.0) >= 0.9
        ):
            recommended_next_family = ""
            rollback_recommendation = "revert_to_v1_learning"
            reasons = ["v1_unstable", "protect_core_execution"]
        elif acceleration.get("phase") == "stabilize_active_multi_strategy":
            recommended_next_family = ""
            reasons = ["stabilize_active_multi_strategy", *list(acceleration.get("reasonCodes") or [])]
        elif acceleration.get("phase") == "stabilize_v1_core":
            recommended_next_family = ""
            reasons = ["v1_unstable", *list(acceleration.get("reasonCodes") or [])]
            rollback_recommendation = "revert_to_v1_learning"
        elif recommended_next_family:
            next_item = next(x for x in items if x["family"] == recommended_next_family)
            reasons = [
                "stable_readiness",
                "launch_acceleration_seed_ready",
                (
                    "telemetry_sufficient"
                    if bool(next_item.get("telemetrySufficient"))
                    else "priority_rollout_order"
                ),
                "capital_ready" if bool(next_item.get("capitalReady")) else "capital_pending",
            ]
        blocked_details = {
            str(i["family"]): {
                "reason_code": primary_readiness_reason(i),
                "blocked_by": blocked_readiness_codes(i),
                "suggested_next_action": str(
                    i.get("suggestedNextAction") or "continue_v1_learning"
                ),
                "capital_truth_reason_codes": list(i.get("capitalTruthReasonCodes") or []),
                "receipt_outcome_truth_reason_codes": list(
                    i.get("receiptOutcomeTruthReasonCodes") or []
                ),
                "global_execution_reason_codes": list(i.get("globalExecutionReasonCodes") or []),
                "internal_prime_reason_codes": list(i.get("internalPrimeReasonCodes") or []),
                "recovery_ready": bool(i.get("recoveryReady", False)),
                "recovery_status": str(i.get("recoveryStatus") or "degraded"),
                "recovery_reason_code": str(i.get("recoveryReasonCode") or ""),
                "recovery_reason_codes": list(i.get("recoveryReasonCodes") or []),
                "recovery_next_action": str(
                    i.get("recoveryNextAction") or i.get("suggestedNextAction") or ""
                ),
                "recovery_freshness_class": str(i.get("recoveryFreshnessClass") or "unknown"),
                "recovery_freshness_reason_code": str(i.get("recoveryFreshnessReasonCode") or "ok"),
                "recovery_freshness_reason_codes": list(
                    i.get("recoveryFreshnessReasonCodes") or []
                ),
                "recovery_freshness_next_action": str(i.get("recoveryFreshnessNextAction") or ""),
                "recovery_history_component": str(i.get("recoveryHistoryComponent") or ""),
                "recovery_history_status": str(i.get("recoveryHistoryStatus") or "steady"),
                "recovery_degraded_since_ts_ms": int(i.get("recoveryDegradedSinceTsMs") or 0),
                "recovery_recovered_at_ts_ms": int(i.get("recoveryRecoveredAtTsMs") or 0),
                "recovery_degraded_duration_ms": int(i.get("recoveryDegradedDurationMs") or 0),
                "recovery_degraded_count": int(i.get("recoveryDegradedCount") or 0),
                "recovery_last_healthy_ts_ms": int(i.get("recoveryLastHealthyTsMs") or 0),
                "recovery_recovered_recently": bool(i.get("recoveryRecoveredRecently", False)),
                "recovery_degradation_severity_class": str(
                    i.get("recoveryDegradationSeverityClass") or "stable"
                ),
                "capital_truth_recovery_history_status": str(
                    i.get("capitalTruthRecoveryHistoryStatus") or "steady"
                ),
                "capital_truth_degraded_since_ts_ms": int(
                    i.get("capitalTruthDegradedSinceTsMs") or 0
                ),
                "capital_truth_recovered_at_ts_ms": int(i.get("capitalTruthRecoveredAtTsMs") or 0),
                "capital_truth_degraded_duration_ms": int(
                    i.get("capitalTruthDegradedDurationMs") or 0
                ),
                "capital_truth_degraded_count": int(i.get("capitalTruthDegradedCount") or 0),
                "capital_truth_last_healthy_ts_ms": int(i.get("capitalTruthLastHealthyTsMs") or 0),
                "capital_truth_recovered_recently": bool(
                    i.get("capitalTruthRecoveredRecently", False)
                ),
                "capital_truth_degradation_severity_class": str(
                    i.get("capitalTruthDegradationSeverityClass") or "stable"
                ),
                "internal_prime_recovery_history_status": str(
                    i.get("internalPrimeRecoveryHistoryStatus") or "steady"
                ),
                "internal_prime_degraded_since_ts_ms": int(
                    i.get("internalPrimeDegradedSinceTsMs") or 0
                ),
                "internal_prime_recovered_at_ts_ms": int(
                    i.get("internalPrimeRecoveredAtTsMs") or 0
                ),
                "internal_prime_degraded_duration_ms": int(
                    i.get("internalPrimeDegradedDurationMs") or 0
                ),
                "internal_prime_degraded_count": int(i.get("internalPrimeDegradedCount") or 0),
                "internal_prime_last_healthy_ts_ms": int(
                    i.get("internalPrimeLastHealthyTsMs") or 0
                ),
                "internal_prime_recovered_recently": bool(
                    i.get("internalPrimeRecoveredRecently", False)
                ),
                "internal_prime_degradation_severity_class": str(
                    i.get("internalPrimeDegradationSeverityClass") or "stable"
                ),
                "capital_truth_reliability_class": str(
                    i.get("capitalTruthReliabilityClass") or "stable"
                ),
                "capital_truth_reliability_reason_code": str(
                    i.get("capitalTruthReliabilityReasonCode") or "ok"
                ),
                "capital_truth_reliability_reason_codes": list(
                    i.get("capitalTruthReliabilityReasonCodes") or []
                ),
                "capital_truth_recovered_fragile": bool(
                    i.get("capitalTruthRecoveredFragile", False)
                ),
                "internal_prime_reliability_class": str(
                    i.get("internalPrimeReliabilityClass") or "stable"
                ),
                "internal_prime_reliability_reason_code": str(
                    i.get("internalPrimeReliabilityReasonCode") or "ok"
                ),
                "internal_prime_reliability_reason_codes": list(
                    i.get("internalPrimeReliabilityReasonCodes") or []
                ),
                "internal_prime_recovered_fragile": bool(
                    i.get("internalPrimeRecoveredFragile", False)
                ),
                "recovery_reliability_class": str(i.get("recoveryReliabilityClass") or "stable"),
                "recovery_reliability_reason_code": str(
                    i.get("recoveryReliabilityReasonCode") or "ok"
                ),
                "recovery_reliability_reason_codes": list(
                    i.get("recoveryReliabilityReasonCodes") or []
                ),
                "recovery_reliability_next_action": str(
                    i.get("recoveryReliabilityNextAction") or i.get("recoveryNextAction") or ""
                ),
                "recovery_recovered_fragile": bool(i.get("recoveryRecoveredFragile", False)),
                "status": str(i.get("status") or "blocked"),
                "degraded_state": str(i.get("degradedState") or ""),
                "launch_acceleration_reason_codes": list(i.get("launchAccelerationReasonCodes") or []),
                "launch_acceleration_stability_reason_codes": list(i.get("launchAccelerationStabilityReasonCodes") or []),
                "launch_acceleration_next_action": str(i.get("launchAccelerationNextAction") or ""),
            }
            for i in locked
            if not i["ready"]
        }
        blocked = {
            family: str(detail.get("reason_code") or "not_recommended")
            for family, detail in blocked_details.items()
        }
        hold_summary = _launch_hold_summary(
            blocked_details=blocked_details,
            recommended_next_family=recommended_next_family,
        )
        acceleration_reason_codes = [
            str(x) for x in list(acceleration.get("reasonCodes") or []) if str(x)
        ]
        if (
            not recommended_next_family
            and acceleration.get("phase") == "stabilize_active_multi_strategy"
            and acceleration_reason_codes
            and str(hold_summary.get("hold_reason_code") or "") in {"", "no_execution_evidence", "execution_not_ready"}
        ):
            hold_summary["hold_reason_code"] = acceleration_reason_codes[0]
            hold_summary["hold_reason_codes"] = acceleration_reason_codes
            hold_summary["suggested_next_action"] = str(
                acceleration.get("nextAction") or hold_summary.get("suggested_next_action") or ""
            )
        elif (
            not recommended_next_family
            and not str(hold_summary.get("hold_reason_code") or "")
            and acceleration_reason_codes
        ):
            hold_summary["hold_reason_code"] = acceleration_reason_codes[0]
            hold_summary["hold_reason_codes"] = acceleration_reason_codes
            hold_summary["suggested_next_action"] = str(
                acceleration.get("nextAction") or hold_summary.get("suggested_next_action") or ""
            )
        graph = CapabilityHealthGraph(
            profile=self.profile.to_dict(), readiness_items=items, stage=stage
        ).snapshot()
        rec = {
            "profile": self.profile.to_dict(),
            "families": items,
            "recommended_next_family": recommended_next_family,
            "reasons": reasons,
            "launch_acceleration": acceleration,
            "launch_acceleration_phase": str(acceleration.get("phase") or "v1_learning"),
            "launch_acceleration_reason_codes": list(acceleration.get("reasonCodes") or []),
            "launch_acceleration_next_action": str(acceleration.get("nextAction") or ""),
            "blocked_families": blocked,
            "blocked_family_details": blocked_details,
            "global_execution_blocked": bool(hold_summary.get("global_execution_blocked", False)),
            "global_execution_reason_codes": list(
                hold_summary.get("global_execution_reason_codes") or []
            ),
            "capital_truth_reason_codes": list(
                hold_summary.get("capital_truth_reason_codes") or []
            ),
            "receipt_outcome_truth_reason_codes": list(
                hold_summary.get("receipt_outcome_truth_reason_codes") or []
            ),
            "internal_prime_reason_codes": list(
                hold_summary.get("internal_prime_reason_codes") or []
            ),
            "hold_reason_code": str(hold_summary.get("hold_reason_code") or ""),
            "hold_reason_codes": list(hold_summary.get("hold_reason_codes") or []),
            "suggested_next_action": str(hold_summary.get("suggested_next_action") or ""),
            "recovery_ready": bool(hold_summary.get("recovery_ready", True)),
            "recovery_status": str(hold_summary.get("recovery_status") or "ready"),
            "recovery_reason_code": str(hold_summary.get("recovery_reason_code") or "ok"),
            "recovery_reason_codes": list(hold_summary.get("recovery_reason_codes") or []),
            "recovery_next_action": str(hold_summary.get("recovery_next_action") or ""),
            "recovery_freshness_class": str(
                hold_summary.get("recovery_freshness_class") or "current"
            ),
            "recovery_freshness_reason_code": str(
                hold_summary.get("recovery_freshness_reason_code") or "ok"
            ),
            "recovery_freshness_reason_codes": list(
                hold_summary.get("recovery_freshness_reason_codes") or []
            ),
            "recovery_freshness_next_action": str(
                hold_summary.get("recovery_freshness_next_action") or ""
            ),
            "recovery_history_component": str(hold_summary.get("recovery_history_component") or ""),
            "recovery_history_status": str(hold_summary.get("recovery_history_status") or "steady"),
            "recovery_degraded_since_ts_ms": int(
                hold_summary.get("recovery_degraded_since_ts_ms") or 0
            ),
            "recovery_recovered_at_ts_ms": int(
                hold_summary.get("recovery_recovered_at_ts_ms") or 0
            ),
            "recovery_degraded_duration_ms": int(
                hold_summary.get("recovery_degraded_duration_ms") or 0
            ),
            "recovery_degraded_count": int(hold_summary.get("recovery_degraded_count") or 0),
            "recovery_last_healthy_ts_ms": int(
                hold_summary.get("recovery_last_healthy_ts_ms") or 0
            ),
            "recovery_recovered_recently": bool(
                hold_summary.get("recovery_recovered_recently", False)
            ),
            "recovery_degradation_severity_class": str(
                hold_summary.get("recovery_degradation_severity_class") or "stable"
            ),
            "recovery_reliability_class": str(
                hold_summary.get("recovery_reliability_class") or "stable"
            ),
            "recovery_reliability_reason_code": str(
                hold_summary.get("recovery_reliability_reason_code") or "ok"
            ),
            "recovery_reliability_reason_codes": list(
                hold_summary.get("recovery_reliability_reason_codes") or []
            ),
            "recovery_reliability_next_action": str(
                hold_summary.get("recovery_reliability_next_action") or ""
            ),
            "recovery_recovered_fragile": bool(
                hold_summary.get("recovery_recovered_fragile", False)
            ),
            "recommended_plan": {
                "next_family": recommended_next_family,
                "why_now": reasons,
                "why_not_others": blocked,
                "why_not_others_details": blocked_details,
                "rollback_recommendation": rollback_recommendation,
                "global_execution_blocked": bool(
                    hold_summary.get("global_execution_blocked", False)
                ),
                "global_execution_reason_codes": list(
                    hold_summary.get("global_execution_reason_codes") or []
                ),
                "capital_truth_reason_codes": list(
                    hold_summary.get("capital_truth_reason_codes") or []
                ),
                "receipt_outcome_truth_reason_codes": list(
                    hold_summary.get("receipt_outcome_truth_reason_codes") or []
                ),
                "internal_prime_reason_codes": list(
                    hold_summary.get("internal_prime_reason_codes") or []
                ),
                "hold_reason_code": str(hold_summary.get("hold_reason_code") or ""),
                "hold_reason_codes": list(hold_summary.get("hold_reason_codes") or []),
                "suggested_next_action": str(hold_summary.get("suggested_next_action") or ""),
                "recovery_ready": bool(hold_summary.get("recovery_ready", True)),
                "recovery_status": str(hold_summary.get("recovery_status") or "ready"),
                "recovery_reason_code": str(hold_summary.get("recovery_reason_code") or "ok"),
                "recovery_reason_codes": list(hold_summary.get("recovery_reason_codes") or []),
                "recovery_next_action": str(hold_summary.get("recovery_next_action") or ""),
                "recovery_freshness_class": str(
                    hold_summary.get("recovery_freshness_class") or "current"
                ),
                "recovery_freshness_reason_code": str(
                    hold_summary.get("recovery_freshness_reason_code") or "ok"
                ),
                "recovery_freshness_reason_codes": list(
                    hold_summary.get("recovery_freshness_reason_codes") or []
                ),
                "recovery_freshness_next_action": str(
                    hold_summary.get("recovery_freshness_next_action") or ""
                ),
                "recovery_history_component": str(
                    hold_summary.get("recovery_history_component") or ""
                ),
                "recovery_history_status": str(
                    hold_summary.get("recovery_history_status") or "steady"
                ),
                "recovery_degraded_since_ts_ms": int(
                    hold_summary.get("recovery_degraded_since_ts_ms") or 0
                ),
                "recovery_recovered_at_ts_ms": int(
                    hold_summary.get("recovery_recovered_at_ts_ms") or 0
                ),
                "recovery_degraded_duration_ms": int(
                    hold_summary.get("recovery_degraded_duration_ms") or 0
                ),
                "recovery_reliability_class": str(
                    hold_summary.get("recovery_reliability_class") or "stable"
                ),
                "recovery_reliability_reason_code": str(
                    hold_summary.get("recovery_reliability_reason_code") or "ok"
                ),
                "recovery_reliability_reason_codes": list(
                    hold_summary.get("recovery_reliability_reason_codes") or []
                ),
                "recovery_reliability_next_action": str(
                    hold_summary.get("recovery_reliability_next_action") or ""
                ),
                "recovery_recovered_fragile": bool(
                    hold_summary.get("recovery_recovered_fragile", False)
                ),
            },
            "health_graph": graph,
        }
        self.profile.last_recommendation = {
            "ts_ms": int(time.time() * 1000),
            "recommended_next_family": recommended_next_family,
            "reasons": reasons,
            "rollback_recommendation": rollback_recommendation,
        }
        self._touch("recommendation_refreshed")
        return rec
