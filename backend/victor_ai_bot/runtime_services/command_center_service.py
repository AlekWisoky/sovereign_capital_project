from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from ..jsonsafe import json_safe
from ..outcomes import GovernanceOutcome
from .auxiliary_state_service import AuxiliaryStateService
from .operator_summary_service import OperatorSummaryService
from .summary_read_contract import build_summary_read_contract


@dataclass(frozen=True)
class CommandCenterPatch:
    patch: Dict[str, Any]
    reason: str


@dataclass(frozen=True)
class CommandCenterResult:
    ok: bool
    payload: Dict[str, Any]
    error: str = ""


class CommandCenterService:
    _REQUEST_META_KEYS = {"patch", "reason"}

    _PATCH_MAPPING = {
        "controlMode": "control_mode",
        "sandboxOnly": "sandbox_only",
        "allocationsFrozen": "allocations_frozen",
        "evolutionFrozen": "evolution_frozen",
        "mutationEnabled": "mutation_enabled",
        "governanceEnabled": "governance_enabled",
        "defensiveMode": "defensive_mode",
        "reduceExposureHalf": "reduce_exposure_half",
        "metricsEnabled": "metrics_enabled",
        "latencyProfilingEnabled": "latency_profiling_enabled",
        "rewardTraceEnabled": "reward_trace_enabled",
        "chaosBreakersEnabled": "chaos_breakers_enabled",
        "rpcBatchEnabled": "rpc_batch_enabled",
        "rftEpisodeExportEnabled": "rft_episode_export_enabled",
        "kellyEnabled": "kelly_enabled",
        "autoReinvestEnabled": "auto_reinvest_enabled",
        "forceSendMode": "force_send_mode",
        "forceGasMode": "force_gas_mode",
        "brainMode": "brain_mode",
        "aggressionMode": "aggression_mode",
        "fullSystemEnabled": "full_system_enabled",
    }

    _POSTURE_WIDENING_KEYS = {
        "paused",
        "control_mode",
        "sandbox_only",
        "allocations_frozen",
        "defensive_mode",
        "reduce_exposure_half",
        "governance_enabled",
        "aggression_mode",
        "full_system_enabled",
        "force_send_mode",
        "force_gas_mode",
    }

    def __init__(self, *, operator_summary: OperatorSummaryService | None = None) -> None:
        self.operator_summary = operator_summary or OperatorSummaryService()

    @staticmethod
    def _invalid_payload(
        reason_code: str, *, details: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "status": "invalid",
            "reason_code": str(reason_code),
            "reason": str(reason_code),
            "error": str(reason_code),
        }
        if details is not None:
            payload["details"] = details
        return payload

    def _normalize_patch_input(self, patch: Mapping[str, Any]) -> Dict[str, Any]:
        return {self._PATCH_MAPPING.get(str(k), str(k)): v for k, v in dict(patch).items()}

    def build_patch(
        self, payload: Mapping[str, Any] | None
    ) -> tuple[CommandCenterPatch | None, Dict[str, Any] | None]:
        if payload is None:
            return None, self._invalid_payload("empty_control_patch")
        if not isinstance(payload, Mapping):
            return None, self._invalid_payload(
                "invalid_control_payload", details={"expected": "object"}
            )
        payload = dict(payload)
        reason = str(payload.get("reason") or "")
        raw_patch = payload.get("patch")
        if "patch" in payload and not isinstance(raw_patch, Mapping):
            return None, self._invalid_payload(
                "invalid_control_patch_payload", details={"field": "patch", "expected": "object"}
            )

        nested_patch = (
            self._normalize_patch_input(raw_patch or {}) if isinstance(raw_patch, Mapping) else {}
        )
        direct_patch = self._normalize_patch_input(
            {k: v for k, v in payload.items() if str(k) not in self._REQUEST_META_KEYS}
        )

        if not nested_patch and not direct_patch:
            return None, self._invalid_payload("empty_control_patch")

        patch = dict(nested_patch)
        for key, value in direct_patch.items():
            if key in patch and patch[key] != value:
                return None, self._invalid_payload(
                    "ambiguous_control_patch",
                    details={"field": key, "nested": patch[key], "direct": value},
                )
            patch.setdefault(key, value)

        requested_mode = (
            str(patch.get("control_mode") or "").strip().lower() if "control_mode" in patch else ""
        )
        if requested_mode == "view_only":
            patch.setdefault("paused", True)
        elif requested_mode in {"assist", "auto"}:
            patch.setdefault("paused", False)
        return CommandCenterPatch(patch=patch, reason=reason), None

    @staticmethod
    def _controls(runtime: Any) -> Any:
        return getattr(getattr(runtime, "_cc", None), "controls", None)

    def _patch_widens_posture(self, *, runtime: Any, patch: Mapping[str, Any]) -> bool:
        controls = self._controls(runtime)
        if controls is None:
            return False
        for key in self._POSTURE_WIDENING_KEYS:
            if key not in patch:
                continue
            current = getattr(controls, key, None)
            incoming = patch[key]
            if key == "paused" and bool(current) and not bool(incoming):
                return True
            if key == "control_mode":
                current_mode = str(current or "").strip().lower()
                incoming_mode = str(incoming or "").strip().lower()
                if current_mode == "view_only" and incoming_mode in {"assist", "auto"}:
                    return True
                if current_mode == "assist" and incoming_mode == "auto":
                    return True
            if key == "sandbox_only" and bool(current) and not bool(incoming):
                return True
            if key == "allocations_frozen" and bool(current) and not bool(incoming):
                return True
            if (
                key in {"defensive_mode", "reduce_exposure_half"}
                and bool(current)
                and not bool(incoming)
            ):
                return True
            if key == "governance_enabled" and bool(current) and not bool(incoming):
                return True
            if key == "aggression_mode":
                current_mode = str(current or "balanced").strip().lower()
                incoming_mode = str(incoming or "balanced").strip().lower()
                if current_mode != "aggressive" and incoming_mode == "aggressive":
                    return True
            if key == "full_system_enabled" and not bool(current) and bool(incoming):
                return True
            if key in {"force_send_mode", "force_gas_mode"} and str(incoming or "").strip():
                return True
        return False

    def _guard_patch(
        self, runtime: Any, *, patch: Mapping[str, Any], reason: str
    ) -> GovernanceOutcome:
        controls = self._controls(runtime)
        if controls is None:
            return GovernanceOutcome(allowed=True, reason_code="allowed")
        widening = self._patch_widens_posture(runtime=runtime, patch=patch)
        if widening and not str(reason or "").strip():
            return GovernanceOutcome(
                allowed=False,
                reason_code="reason_required_for_posture_widening",
                review_required=True,
            )
        if widening and not bool(getattr(controls, "mutation_enabled", False)):
            return GovernanceOutcome(
                allowed=False,
                reason_code="mutation_disabled",
                review_required=True,
                details={"requiredControl": "mutation_enabled"},
            )
        if widening and not bool(getattr(controls, "governance_enabled", True)):
            return GovernanceOutcome(
                allowed=False,
                reason_code="governance_disabled",
                review_required=True,
                details={"requiredControl": "governance_enabled"},
            )
        if patch.get("governance_enabled") is False and not bool(
            getattr(controls, "paused", False)
        ):
            return GovernanceOutcome(
                allowed=False,
                reason_code="pause_required_before_governance_disable",
                review_required=True,
            )
        if patch.get("full_system_enabled") is True and bool(patch.get("sandbox_only", False)):
            return GovernanceOutcome(
                allowed=False,
                reason_code="full_system_requires_live_posture",
                review_required=False,
            )
        if patch.get("control_mode") == "auto" and bool(
            getattr(controls, "allocations_frozen", False)
        ):
            return GovernanceOutcome(
                allowed=False,
                reason_code="allocations_frozen",
                review_required=False,
            )
        if patch.get("control_mode") == "auto":
            policy = AuxiliaryStateService().capital_policy(runtime)
            cc_policy = (
                dict((policy or {}).get("commandCenter") or {}) if isinstance(policy, dict) else {}
            )
            if cc_policy and not bool(cc_policy.get("autoAllowed", True)):
                blockers = [str(x) for x in list(cc_policy.get("autoBlockers") or []) if str(x)]
                return GovernanceOutcome(
                    allowed=False,
                    reason_code=str(blockers[0] if blockers else "capital_nav_unavailable"),
                    review_required=False,
                    details={"capitalPolicy": policy},
                )
        return GovernanceOutcome(allowed=True, reason_code="allowed")

    async def snapshot(self, runtime: Any) -> Dict[str, Any]:
        payload = json_safe(await self.operator_summary.build_snapshot(runtime))
        operator_summary_contract = dict(payload.get("summaryContract") or {})
        service_contracts = dict(payload.get("serviceContracts") or {})
        if operator_summary_contract:
            service_contracts["operatorSummary"] = operator_summary_contract
            payload["serviceContracts"] = service_contracts
        payload["summaryContract"] = build_summary_read_contract(
            family="command_center",
            payload=payload,
            capital_contract=dict(payload.get("capitalContract") or {}),
            capital_policy=dict(payload.get("capitalPolicy") or {}),
            source_contracts={
                "operatorSummary": operator_summary_contract,
                "capitalContract": dict(payload.get("capitalContract") or {}),
                "capitalPolicy": dict(payload.get("capitalPolicy") or {}),
                "capitalTruth": dict(
                    (payload.get("capitalTruthHealth") or {}).get("stateContract") or {}
                ),
            },
            phase="command_center_summary",
        )
        return json_safe(payload)

    def audit_tail(self, runtime: Any, limit: int) -> Dict[str, Any]:
        return self.operator_summary.audit_tail(runtime, limit=limit)

    async def explain(self, runtime: Any) -> Dict[str, Any]:
        return await self.operator_summary.explain(runtime)

    def apply_controls(
        self, runtime: Any, payload: Mapping[str, Any] | None
    ) -> CommandCenterResult:
        cc = getattr(runtime, "_cc", None)
        if cc is None:
            return CommandCenterResult(
                ok=False,
                payload={"ok": False, "error": "commandcenter_unavailable"},
                error="commandcenter_unavailable",
            )
        built, invalid = self.build_patch(payload)
        if built is None:
            invalid_payload = invalid or self._invalid_payload("invalid_control_patch")
            return CommandCenterResult(
                ok=False,
                payload=invalid_payload,
                error=str(
                    invalid_payload.get("reason_code")
                    or invalid_payload.get("error")
                    or "invalid_control_patch"
                ),
            )
        outcome = self._guard_patch(runtime, patch=built.patch, reason=built.reason)
        if not outcome.allowed:
            payload = {"ok": False, **json_safe(outcome.to_dict())}
            details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
            if isinstance(details, dict) and isinstance(details.get("capitalPolicy"), dict):
                payload["capitalPolicy"] = dict(details.get("capitalPolicy") or {})
            return CommandCenterResult(
                ok=False,
                payload=payload,
                error=str(outcome.reason_code),
            )
        result = json_safe(cc.set_controls(built.patch, actor="operator", reason=built.reason))
        if not bool(result.get("ok", False)):
            error = str(
                result.get("reason_code") or result.get("error") or "commandcenter_control_failed"
            )
            return CommandCenterResult(ok=False, payload=result, error=error)
        controls = getattr(cc, "controls", None)
        if "paused" in built.patch:
            runtime.set_settings(auto_trading=not bool(getattr(controls, "paused", False)))
        return CommandCenterResult(ok=True, payload=result)
