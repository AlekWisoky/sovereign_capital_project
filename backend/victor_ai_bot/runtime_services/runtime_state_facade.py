from __future__ import annotations

from typing import Any, Dict, Optional

from ..jsonsafe import to_json_safe
from .control_state import unavailable_state
from .runtime_context import public_mode_for_capture as service_public_mode_for_capture
from .fund_service import fund_summary_unavailable_payload
from .family_hardening_service import family_hardening_unavailable_summary

_RUNTIME_STATE_FACADE_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeStateFacade:
    """Non-hot-path runtime state/reporting compatibility facade.

    This isolates dashboard, analytics, and operator summary accessors away from
    RuntimeBundle's orchestration loop while preserving the public method surface.
    """

    # RuntimeStateFacade is mixed into the runtime aggregate rather than owning
    # these services itself. Declare the injected dependency here so static type
    # checkers understand the runtime-composition contract used by the facade.
    _auxiliary_state_service: Any

    @staticmethod
    def _unavailable_state(
        reason_code: str,
        *,
        extra: Optional[Dict[str, Any]] = None,
        include_reason: bool = True,
        include_error: bool = False,
        include_text: bool = False,
    ) -> Dict[str, Any]:
        return unavailable_state(
            reason_code,
            extra=extra,
            include_reason=include_reason,
            include_error=include_error,
            include_text=include_text,
        )

    def _auxiliary_state_payload(
        self,
        method_name: str,
        *,
        default: Dict[str, Any],
        args: tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        service = getattr(self, "_auxiliary_state_service", None)
        if service is None or not hasattr(service, method_name):
            return to_json_safe(dict(default))
        try:
            payload = getattr(service, method_name)(self, *args, **(kwargs or {}))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return to_json_safe(dict(default))
        return to_json_safe(payload)

    def _service_payload(
        self,
        service_attr: str,
        *,
        method_name: str,
        default: Dict[str, Any],
        args: tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        service = getattr(self, service_attr, None)
        if service is None or not hasattr(service, method_name):
            return to_json_safe(dict(default))
        try:
            payload = getattr(service, method_name)(*args, **(kwargs or {}))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return to_json_safe(dict(default))
        return to_json_safe(payload)

    async def _async_service_payload(
        self,
        service_attr: str,
        *,
        method_name: str,
        default: Dict[str, Any],
        args: tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        service = getattr(self, service_attr, None)
        if service is None or not hasattr(service, method_name):
            return to_json_safe(dict(default))
        try:
            payload = await getattr(service, method_name)(*args, **(kwargs or {}))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return to_json_safe(dict(default))
        return to_json_safe(payload)

    def _state_summary_payload(
        self,
        method_name: str,
        *,
        default: Dict[str, Any],
        args: tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        service = getattr(self, "_state_summary_service", None)
        if service is None or not hasattr(service, method_name):
            return to_json_safe(dict(default))
        try:
            payload = getattr(service, method_name)(self, *args, **(kwargs or {}))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return to_json_safe(dict(default))
        return to_json_safe(payload)

    def execution_capture_analytics(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "execution_capture_analytics",
            default={"laneSuccess": [], "venueQuality": []},
        )

    def telemetry_summary(self) -> Dict[str, Any]:
        return self._service_payload(
            "_telemetry_service",
            method_name="summary",
            default={"realization": {"families": []}, "agents": {"agents": []}},
        )

    def execution_calibration_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("execution_calibration", default={"items": []})

    def venue_profiles_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("venue_profiles", default={"venues": []})

    def endpoint_quality_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "endpoint_quality",
            default={"lanes": {}, "relays": {}},
        )

    def venue_scorecards_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("venue_scorecards", default={"items": []})

    def endpoint_universe_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "endpoint_universe",
            default={"read": {}, "public": {}, "protected": {}, "private": {}},
        )

    def execution_live_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("execution_live", default={"items": []})

    def route_quality_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("route_quality", default={"items": []})

    def drawdown_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "drawdown",
            default={
                "drawdownPct": 0.0,
                "intradayLossUsd": 0.0,
                "familyDrawdown": {},
                "hardStop": {"active": False, "reason_codes": []},
            },
        )

    def kill_switch_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "kill_switch",
            default={"metrics": {}, "suppressions": {}, "history": []},
        )

    def risk_memory_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("risk_memory", default={"failures": {}})

    def path_diversity_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("path_diversity", default={"paths": []})

    def edge_learning_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "edge_learning",
            default={"items": [], "quarantine": {}, "explorationBudget": {}},
        )

    def launch_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "launch",
            default=self._unavailable_state("launch_service_unavailable"),
        )

    def rpc_preferences_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "rpc_preferences",
            default={"read": [], "send": [], "private": [], "configured": False},
        )

    def strategy_scorecards_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("strategy_scorecards", default={"families": []})

    def agent_attribution_state(self) -> Dict[str, Any]:
        return self._state_summary_payload("agent_attribution", default={"agents": []})

    def engine_state(self) -> Dict[str, Any]:
        return to_json_safe(
            dict(
                getattr(self, "_engine_last", {})
                or {"items": [], "capabilities": {}, "summary": {"engines": []}}
            )
        )

    def capital_engine_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "capital_engine",
            default={
                "capital_engine": {},
                "reinvestment_policy": {},
                "capital_efficiency_metrics": {},
            },
        )

    def fund_summary_state(self) -> Dict[str, Any]:
        return self._state_summary_payload(
            "fund_summary",
            default=fund_summary_unavailable_payload(self),
        )

    def research_pipeline_state(self) -> Dict[str, Any]:
        return self._auxiliary_state_payload(
            "research_pipeline_state",
            default={"items": [], "pipelineCounts": {}, "throughput": {}},
        )

    def doctrine_state(self) -> Dict[str, Any]:
        return self._auxiliary_state_payload(
            "doctrine_state",
            default={"optimizationObjectives": {}},
        )

    def ledger_state(self) -> Dict[str, Any]:
        return self._auxiliary_state_payload(
            "ledger_state",
            default={"balances": {}, "tail": [], "transactions": []},
        )

    def internal_prime_state(self) -> Dict[str, Any]:
        return self._auxiliary_state_payload(
            "internal_prime_state",
            default={
                "ok": False,
                "status": "unavailable",
                "reason_code": "internal_prime_unavailable",
                "reason": "internal_prime_unavailable",
                "borrowedUsd": 0.0,
                "capacityUsd": 0.0,
                "utilization": 0.0,
                "inventory": {},
                "familyExposure": {},
                "openLoans": [],
                "disputedLoans": [],
                "loanCount": 0,
                "disputedLoanCount": 0,
                "stateReady": False,
                "stateStatus": "unavailable",
                "stateReasonCode": "internal_prime_unavailable",
                "stateReason": "internal_prime_unavailable",
            },
        )

    def cio_summary_state(self) -> Dict[str, Any]:
        return self._auxiliary_state_payload(
            "cio_summary_state",
            default=self._unavailable_state("cio_service_unavailable"),
        )

    def fund_state(self) -> Dict[str, Any]:
        return self.fund_summary_state()

    def family_hardening_state(self) -> Dict[str, Any]:
        return self._service_payload(
            "_family_hardening_service",
            method_name="summary",
            default=family_hardening_unavailable_summary(),
            args=(self,),
        )

    def capital_truth(self):
        return self._auxiliary_state_service.capital_truth(self)

    def capital_summary(self) -> Dict[str, Any]:
        return self.capital_truth().capital_summary

    def capital_contract(self) -> Dict[str, Any]:
        return self.capital_truth().capital_contract

    def capital_policy(self) -> Dict[str, Any]:
        return self._auxiliary_state_service.capital_policy(self)

    def capital_truth_state(self) -> Dict[str, Any]:
        return self._service_payload(
            "_capital_truth_service",
            method_name="summary",
            default=self._unavailable_state("capital_truth_service_unavailable"),
            args=(self,),
        )

    async def withdraw_all_state(self) -> Dict[str, Any]:
        return await self._async_service_payload(
            "_withdraw_all_service",
            method_name="state",
            default=self._unavailable_state("withdraw_all_service_unavailable"),
            args=(self,),
        )

    def metrics_state(self) -> dict:
        """Best-effort metrics snapshot for AQE/meta layers."""
        aux = getattr(self, "_auxiliary_state_service", None)
        if aux is None or not hasattr(aux, "metrics_state"):
            return {}
        try:
            return to_json_safe(aux.metrics_state(self))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return {}

    def brain_state(self) -> dict:
        decision = getattr(self, "_decision", None)
        if decision is None or not hasattr(decision, "brain_state"):
            return {}
        try:
            return to_json_safe(decision.brain_state())
        except _RUNTIME_STATE_FACADE_FAILURES:
            return {}

    def unified_state(self) -> Dict[str, Any]:
        return self._auxiliary_state_payload(
            "unified_state",
            default=self._unavailable_state("unified_state_unavailable", extra={"enabled": False}),
        )

    def spread_opportunities(self) -> Dict[str, Any]:
        return self._auxiliary_state_payload(
            "spread_opportunities",
            default={"opportunities": []},
        )
