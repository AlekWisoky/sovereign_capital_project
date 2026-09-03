from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from typing import Any, Dict

from ..api_facades.launch_facade import build_launch_context, guard_launch_mutation
from ..fund_os.family_identity import canonical_launch_family_id
from .control_state import unavailable_state
from .family_hardening_service import family_hardening_unavailable_summary
from .auxiliary_state_service import AuxiliaryStateService
from .summary_read_contract import build_summary_read_contract

_LAUNCH_COMPONENT_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _family_hardening_unavailable_payload(family: str | None = None) -> Dict[str, Any]:
    return family_hardening_unavailable_summary(family)


def _family_hardening_payload(runtime: Any, family: str | None = None) -> Dict[str, Any] | None:
    service = getattr(runtime, "_family_hardening_service", None)
    if service is None:
        return None
    method_name = "family_state" if family else "summary"
    if not hasattr(service, method_name):
        return _family_hardening_unavailable_payload(family)
    try:
        payload = (
            getattr(service, method_name)(runtime, str(family))
            if family
            else getattr(service, method_name)(runtime)
        )
    except _LAUNCH_COMPONENT_FAILURES:
        return _family_hardening_unavailable_payload(family)
    if isinstance(payload, ABCMapping):
        return dict(payload)
    return _family_hardening_unavailable_payload(family)


class LaunchService:
    def __init__(self, *, auxiliary_state: AuxiliaryStateService | None = None) -> None:
        self.auxiliary_state = auxiliary_state or AuxiliaryStateService()

    @staticmethod
    def _rollout(runtime: Any) -> Any | None:
        return getattr(runtime, "_launch_rollout", None)

    def _unavailable(self, runtime: Any, family: str | None = None) -> Dict[str, Any]:
        return self._with_family_hardening(
            runtime, unavailable_state("launch_rollout_unavailable"), family
        )

    @staticmethod
    def _context(runtime: Any) -> Dict[str, Any]:
        return build_launch_context(runtime)

    @staticmethod
    def _with_family_hardening(
        runtime: Any, payload: Dict[str, Any], family: str | None = None
    ) -> Dict[str, Any]:
        hardening = _family_hardening_payload(runtime, family if family else None)
        if hardening is None:
            return payload
        if family:
            payload["hardening"] = hardening
        else:
            payload["familyHardening"] = hardening
        return payload

    def summary(self, runtime: Any) -> Dict[str, Any]:
        rollout = self._rollout(runtime)
        if rollout is None:
            return self._unavailable(runtime)
        ctx = self._context(runtime)
        capital_policy = self.auxiliary_state.capital_policy(runtime)
        payload = {
            "ok": True,
            "capitalPolicy": capital_policy,
            **rollout.recommendation(
                stage=ctx["stage"],
                scorecards=ctx["scorecards"],
                engine_state=ctx["engine_state"],
                telemetry=ctx["telemetry"],
                calibration=ctx["calibration"],
                fund_summary=ctx["fund_summary"],
                capital_state=ctx["capital_state"],
            ),
        }
        payload = self._with_family_hardening(runtime, payload)
        payload["summaryContract"] = build_summary_read_contract(
            family="launch",
            payload=payload,
            capital_policy=dict(payload.get("capitalPolicy") or {}),
            source_contracts={
                "familyHardening": dict(payload.get("familyHardening") or {}),
            },
            phase="launch_summary",
            read_model="launch_summary_projection_v1",
        )
        return payload

    def set_mode(self, runtime: Any, mode: str) -> Dict[str, Any]:
        rollout = self._rollout(runtime)
        if rollout is None:
            return self._unavailable(runtime)
        outcome = guard_launch_mutation(runtime=runtime, family="", action="set_mode")
        if not outcome.allowed:
            payload = {
                "ok": False,
                **outcome.to_dict(),
                "capitalPolicy": self.auxiliary_state.capital_policy(runtime),
            }
            return self._with_family_hardening(runtime, payload)
        return self._with_family_hardening(
            runtime,
            {"ok": True, "profile": rollout.set_mode(str(mode or "V1_ONLY"))},
        )

    def enable_next(self, runtime: Any, requested_family: str = "") -> Dict[str, Any]:
        rollout = self._rollout(runtime)
        if rollout is None:
            return self._unavailable(runtime)
        ctx = self._context(runtime)
        launch = rollout.recommendation(
            stage=ctx["stage"],
            scorecards=ctx["scorecards"],
            engine_state=ctx["engine_state"],
            telemetry=ctx["telemetry"],
            calibration=ctx["calibration"],
            fund_summary=ctx["fund_summary"],
            capital_state=ctx["capital_state"],
        )
        family = canonical_launch_family_id(
            str(requested_family or launch.get("recommended_next_family") or "")
        )
        if not family:
            return {
                "ok": False,
                "reason_code": "no_recommended_family",
                "launch": launch,
                "capitalPolicy": self.auxiliary_state.capital_policy(runtime),
            }
        outcome = guard_launch_mutation(runtime=runtime, family=family, action="enable_next")
        if not outcome.allowed:
            return self._with_family_hardening(
                runtime,
                {
                    "ok": False,
                    **outcome.to_dict(),
                    "launch": launch,
                    "capitalPolicy": self.auxiliary_state.capital_policy(runtime),
                },
                family,
            )
        out = rollout.enable_family(
            family,
            stage=ctx["stage"],
            scorecards=ctx["scorecards"],
            engine_state=ctx["engine_state"],
            telemetry=ctx["telemetry"],
            calibration=ctx["calibration"],
            fund_summary=ctx["fund_summary"],
            capital_state=ctx["capital_state"],
        )
        payload = dict(out or {})
        payload["launch"] = launch
        payload["capitalPolicy"] = self.auxiliary_state.capital_policy(runtime)
        return self._with_family_hardening(runtime, payload, family)

    def pause_family(self, runtime: Any, family: str) -> Dict[str, Any]:
        rollout = self._rollout(runtime)
        family = canonical_launch_family_id(str(family or ""))
        if rollout is None:
            return self._unavailable(runtime, family)
        outcome = guard_launch_mutation(runtime=runtime, family=family, action="pause_family")
        if not outcome.allowed:
            return self._with_family_hardening(
                runtime,
                {
                    "ok": False,
                    **outcome.to_dict(),
                    "capitalPolicy": self.auxiliary_state.capital_policy(runtime),
                },
                family,
            )
        return self._with_family_hardening(runtime, rollout.pause_family(family), family)

    def revert_family(self, runtime: Any, family: str) -> Dict[str, Any]:
        rollout = self._rollout(runtime)
        family = canonical_launch_family_id(str(family or ""))
        if rollout is None:
            return self._unavailable(runtime, family)
        outcome = guard_launch_mutation(runtime=runtime, family=family, action="revert_family")
        if not outcome.allowed:
            return self._with_family_hardening(
                runtime,
                {
                    "ok": False,
                    **outcome.to_dict(),
                    "capitalPolicy": self.auxiliary_state.capital_policy(runtime),
                },
                family,
            )
        return self._with_family_hardening(runtime, rollout.revert_family(family), family)

    def quarantine_family(self, runtime: Any, family: str, *, reason_code: str) -> Dict[str, Any]:
        rollout = self._rollout(runtime)
        family = canonical_launch_family_id(str(family or ""))
        if rollout is None:
            return self._unavailable(runtime, family)
        outcome = guard_launch_mutation(runtime=runtime, family=family, action="quarantine_family")
        if not outcome.allowed:
            return self._with_family_hardening(
                runtime,
                {
                    "ok": False,
                    **outcome.to_dict(),
                    "capitalPolicy": self.auxiliary_state.capital_policy(runtime),
                },
                family,
            )
        return self._with_family_hardening(
            runtime,
            rollout.quarantine_family(
                family,
                actor="operator",
                reason_code=str(reason_code or "operator_quarantine"),
            ),
            family,
        )

    def family_detail(self, runtime: Any, family: str) -> Dict[str, Any]:
        family = canonical_launch_family_id(str(family or ""))
        rollout = self._rollout(runtime)
        if rollout is None:
            return self._unavailable(runtime, family)
        ctx = self._context(runtime)
        payload = rollout.family_detail(
            family,
            stage=ctx["stage"],
            scorecards=ctx["scorecards"],
            engine_state=ctx["engine_state"],
            telemetry=ctx["telemetry"],
            calibration=ctx["calibration"],
            fund_summary=ctx["fund_summary"],
            capital_state=ctx["capital_state"],
        )
        if isinstance(payload, dict):
            payload["capitalPolicy"] = self.auxiliary_state.capital_policy(runtime)
        payload = self._with_family_hardening(runtime, payload, family)
        payload["summaryContract"] = build_summary_read_contract(
            family="launch_family",
            payload=payload,
            capital_policy=dict(payload.get("capitalPolicy") or {}),
            source_contracts={
                "hardening": dict(payload.get("hardening") or {}),
            },
            phase="launch_family_summary",
            read_model="launch_family_projection_v1",
        )
        return payload
