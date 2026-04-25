from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ..jsonsafe import to_json_safe
from .control_state import unavailable_state
from .fund_service import fund_summary_unavailable_payload
from .family_hardening_service import family_hardening_unavailable_summary

_STATE_SUMMARY_COMPONENT_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


@dataclass(frozen=True)
class ServiceSnapshotDefaults:
    venue_scorecards: Dict[str, Any] = None  # type: ignore[assignment]
    endpoint_universe: Dict[str, Any] = None  # type: ignore[assignment]
    execution_live: Dict[str, Any] = None  # type: ignore[assignment]
    route_quality: Dict[str, Any] = None  # type: ignore[assignment]
    drawdown: Dict[str, Any] = None  # type: ignore[assignment]
    kill_switch: Dict[str, Any] = None  # type: ignore[assignment]
    risk_memory: Dict[str, Any] = None  # type: ignore[assignment]
    path_diversity: Dict[str, Any] = None  # type: ignore[assignment]
    edge_learning: Dict[str, Any] = None  # type: ignore[assignment]
    rpc_preferences: Dict[str, Any] = None  # type: ignore[assignment]
    agent_attribution: Dict[str, Any] = None  # type: ignore[assignment]
    fund_summary: Dict[str, Any] = None  # type: ignore[assignment]
    analytics: Dict[str, Any] = None  # type: ignore[assignment]
    receipt_summary: Dict[str, Any] = None  # type: ignore[assignment]
    capital_summary: Dict[str, Any] = None  # type: ignore[assignment]
    capital_truth_state: Dict[str, Any] = None  # type: ignore[assignment]
    capital_explain: Dict[str, Any] = None  # type: ignore[assignment]
    services: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self):
        object.__setattr__(
            self,
            "venue_scorecards",
            {"items": []} if self.venue_scorecards is None else self.venue_scorecards,
        )
        object.__setattr__(
            self,
            "endpoint_universe",
            (
                {"read": {}, "public": {}, "protected": {}, "private": {}}
                if self.endpoint_universe is None
                else self.endpoint_universe
            ),
        )
        object.__setattr__(
            self,
            "execution_live",
            {"items": []} if self.execution_live is None else self.execution_live,
        )
        object.__setattr__(
            self,
            "route_quality",
            {"items": []} if self.route_quality is None else self.route_quality,
        )
        object.__setattr__(
            self,
            "drawdown",
            (
                {
                    "drawdownPct": 0.0,
                    "intradayLossUsd": 0.0,
                    "familyDrawdown": {},
                    "hardStop": {"active": False, "reason_codes": []},
                }
                if self.drawdown is None
                else self.drawdown
            ),
        )
        object.__setattr__(
            self,
            "kill_switch",
            (
                {"metrics": {}, "suppressions": {}, "history": []}
                if self.kill_switch is None
                else self.kill_switch
            ),
        )
        object.__setattr__(
            self, "risk_memory", {"failures": {}} if self.risk_memory is None else self.risk_memory
        )
        object.__setattr__(
            self,
            "path_diversity",
            {"paths": []} if self.path_diversity is None else self.path_diversity,
        )
        object.__setattr__(
            self,
            "edge_learning",
            (
                {"items": [], "quarantine": {}, "explorationBudget": {}}
                if self.edge_learning is None
                else self.edge_learning
            ),
        )
        object.__setattr__(
            self,
            "rpc_preferences",
            (
                {"read": [], "send": [], "private": [], "configured": False}
                if self.rpc_preferences is None
                else self.rpc_preferences
            ),
        )
        object.__setattr__(
            self,
            "agent_attribution",
            {"agents": []} if self.agent_attribution is None else self.agent_attribution,
        )
        object.__setattr__(
            self,
            "fund_summary",
            (
                fund_summary_unavailable_payload()
                if self.fund_summary is None
                else self.fund_summary
            ),
        )
        object.__setattr__(
            self,
            "analytics",
            (
                unavailable_state(
                    "analytics_service_unavailable", include_reason=False, include_error=True
                )
                if self.analytics is None
                else self.analytics
            ),
        )
        object.__setattr__(
            self,
            "receipt_summary",
            (
                unavailable_state(
                    "receipt_service_unavailable", include_reason=False, include_error=True
                )
                if self.receipt_summary is None
                else self.receipt_summary
            ),
        )
        object.__setattr__(
            self,
            "capital_summary",
            (
                unavailable_state(
                    "capital_summary_unavailable", include_reason=False, include_error=True
                )
                if self.capital_summary is None
                else self.capital_summary
            ),
        )
        object.__setattr__(
            self,
            "capital_truth_state",
            (
                unavailable_state(
                    "capital_truth_service_unavailable", include_reason=False, include_error=True
                )
                if self.capital_truth_state is None
                else self.capital_truth_state
            ),
        )
        object.__setattr__(
            self,
            "capital_explain",
            (
                unavailable_state(
                    "capital_explanation_unavailable",
                    extra={"facts": {}, "causal": {}},
                    include_reason=False,
                    include_text=True,
                )
                if self.capital_explain is None
                else self.capital_explain
            ),
        )
        object.__setattr__(
            self,
            "services",
            (
                {
                    "admission": unavailable_state("admission_service_unavailable"),
                    "execution": unavailable_state("execution_service_unavailable"),
                    "receipt": unavailable_state("receipt_service_unavailable"),
                    "telemetry": unavailable_state("telemetry_service_unavailable"),
                    "wealthGoal": unavailable_state("wealth_goal_service_unavailable"),
                    "replay": unavailable_state("replay_service_unavailable"),
                }
                if self.services is None
                else self.services
            ),
        )


class StateSummaryService:
    def __init__(self, defaults: ServiceSnapshotDefaults | None = None) -> None:
        self.defaults = defaults or ServiceSnapshotDefaults()

    @staticmethod
    def _snapshot(
        store: Any, *, method: str = "snapshot", default: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        if store is None or not hasattr(store, method):
            return dict(default or {})
        try:
            value = getattr(store, method)()
            return to_json_safe(value if isinstance(value, dict) else dict(value or {}))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return dict(default or {})

    def venue_scorecards(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_venue_scorecards", None), default=self.defaults.venue_scorecards
        )

    def endpoint_universe(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_endpoint_universe", None), default=self.defaults.endpoint_universe
        )

    def execution_live(self, runtime: Any) -> Dict[str, Any]:
        svc = getattr(runtime, "_execution_service", None)
        if svc is None or not hasattr(svc, "build_live_state"):
            return dict(self.defaults.execution_live)
        try:
            return to_json_safe(svc.build_live_state(runtime))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return dict(self.defaults.execution_live)

    def route_quality(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_route_quality", None), default=self.defaults.route_quality
        )

    def drawdown(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_drawdown_state", None), default=self.defaults.drawdown
        )

    def kill_switch(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_kill_switch", None), default=self.defaults.kill_switch
        )

    def risk_memory(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_risk_memory", None), default=self.defaults.risk_memory
        )

    def path_diversity(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_path_diversity", None), default=self.defaults.path_diversity
        )

    def edge_learning(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_edge_learning", None), default=self.defaults.edge_learning
        )

    def rpc_preferences(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_rpc_preferences", None), default=self.defaults.rpc_preferences
        )

    def agent_attribution(self, runtime: Any) -> Dict[str, Any]:
        store = getattr(runtime, "_agent_attribution", None)
        if store is None or not hasattr(store, "summary"):
            return dict(self.defaults.agent_attribution)
        try:
            return to_json_safe(store.summary())
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return dict(self.defaults.agent_attribution)

    def fund_summary(self, runtime: Any) -> Dict[str, Any]:
        svc = getattr(runtime, "_fund_service", None)
        if svc is None or not hasattr(svc, "summary"):
            return fund_summary_unavailable_payload(runtime)
        try:
            return to_json_safe(svc.summary(runtime))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return fund_summary_unavailable_payload(runtime)

    def analytics(self, runtime: Any) -> Dict[str, Any]:
        svc = getattr(runtime, "_analytics_service", None)
        if svc is None or not hasattr(svc, "system_summary"):
            return dict(self.defaults.analytics)
        try:
            return to_json_safe(svc.system_summary(runtime))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return dict(self.defaults.analytics)

    def receipt_summary(self, runtime: Any) -> Dict[str, Any]:
        svc = getattr(runtime, "_receipt_service", None)
        if svc is None or not hasattr(svc, "summarize"):
            return dict(self.defaults.receipt_summary)
        try:
            return to_json_safe(svc.summarize(runtime))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return dict(self.defaults.receipt_summary)

    def capital_summary(self, runtime: Any) -> Dict[str, Any]:
        if not hasattr(runtime, "capital_summary"):
            return dict(self.defaults.capital_summary)
        try:
            return to_json_safe(runtime.capital_summary())
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return dict(self.defaults.capital_summary)

    def capital_truth_state(self, runtime: Any) -> Dict[str, Any]:
        if not hasattr(runtime, "capital_truth_state"):
            return dict(self.defaults.capital_truth_state)
        try:
            return to_json_safe(runtime.capital_truth_state())
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return dict(self.defaults.capital_truth_state)

    def capital_explain(
        self, runtime: Any, snapshot: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        svc = getattr(runtime, "_capital_explanation_service", None)
        if svc is None or not hasattr(svc, "explain"):
            return dict(self.defaults.capital_explain)
        try:
            return to_json_safe(svc.explain(runtime, snapshot=snapshot or {}))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return dict(self.defaults.capital_explain)

    def replay_state(self, runtime: Any) -> Dict[str, Any]:
        replay = getattr(runtime, "_replay", None)
        if replay is None or not hasattr(replay, "state"):
            return {}
        try:
            state = replay.state()
            return to_json_safe(state if isinstance(state, dict) else dict(state or {}))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return {}

    def pnl_state(self, runtime: Any) -> Dict[str, Any]:
        store = getattr(runtime, "_pnl", None)
        if store is None or not hasattr(store, "state"):
            return {}
        try:
            state = store.state()
            return to_json_safe(state if isinstance(state, dict) else dict(state or {}))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return {}

    @staticmethod
    def _storage_reason_code(storage_state: Dict[str, Any]) -> str:
        if not isinstance(storage_state, dict) or not bool(storage_state.get("degraded", False)):
            return ""
        for value in storage_state.values():
            if isinstance(value, dict):
                code = str(value.get("last_error_code") or "")
                if code:
                    return code
        return "storage_degraded"

    def _storage_service_health_payload(
        self,
        existing: Dict[str, Any] | None,
        *,
        service_present: bool,
        service_unavailable_reason_code: str,
        storage_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = dict(existing or {})
        degraded = bool(storage_state.get("degraded", False))
        payload["ok"] = bool(service_present)
        payload["storage"] = dict(storage_state)
        payload["degraded"] = degraded
        if service_present:
            reason_code = self._storage_reason_code(storage_state) if degraded else "ok"
            payload["status"] = "degraded" if degraded else "ok"
            payload["reason_code"] = reason_code
            payload["reason"] = reason_code
            payload.pop("error", None)
            return payload

        unavailable = unavailable_state(service_unavailable_reason_code)
        unavailable["storage"] = dict(storage_state)
        unavailable["degraded"] = degraded
        return unavailable

    def service_health(self, runtime: Any) -> Dict[str, Any]:
        replay_state = self.replay_state(runtime)
        pnl_state = self.pnl_state(runtime)
        svc = getattr(runtime, "_telemetry_service", None)
        if svc is not None and hasattr(svc, "service_health"):
            try:
                payload = to_json_safe(svc.service_health(runtime))
                for key, default_payload in self.defaults.services.items():
                    payload.setdefault(key, dict(default_payload))
                if replay_state:
                    payload["replay"] = self._storage_service_health_payload(
                        payload.get("replay") if isinstance(payload.get("replay"), dict) else None,
                        service_present=bool(getattr(runtime, "_replay_service", None) is not None),
                        service_unavailable_reason_code="replay_service_unavailable",
                        storage_state=replay_state,
                    )
                if pnl_state:
                    payload["pnl"] = self._storage_service_health_payload(
                        payload.get("pnl") if isinstance(payload.get("pnl"), dict) else None,
                        service_present=bool(getattr(runtime, "_pnl", None) is not None),
                        service_unavailable_reason_code="pnl_service_unavailable",
                        storage_state=pnl_state,
                    )
                return payload
            except _STATE_SUMMARY_COMPONENT_FAILURES:
                pass
        payload = dict(self.defaults.services)
        if replay_state:
            payload["replay"] = self._storage_service_health_payload(
                payload.get("replay") if isinstance(payload.get("replay"), dict) else None,
                service_present=bool(getattr(runtime, "_replay_service", None) is not None),
                service_unavailable_reason_code="replay_service_unavailable",
                storage_state=replay_state,
            )
        if pnl_state:
            payload["pnl"] = self._storage_service_health_payload(
                payload.get("pnl") if isinstance(payload.get("pnl"), dict) else None,
                service_present=bool(getattr(runtime, "_pnl", None) is not None),
                service_unavailable_reason_code="pnl_service_unavailable",
                storage_state=pnl_state,
            )
        return payload

    def execution_capture_analytics(self, runtime: Any) -> Dict[str, Any]:
        store = getattr(runtime, "_capture_telemetry", None)
        if store is None or not hasattr(store, "analytics_series"):
            return {"laneSuccess": [], "venueQuality": []}
        try:
            return to_json_safe(store.analytics_series())
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return {"laneSuccess": [], "venueQuality": []}

    def execution_calibration(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_execution_calibration", None), default={"items": []}
        )

    def venue_profiles(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(getattr(runtime, "_venue_profiles", None), default={"venues": []})

    def endpoint_quality(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_endpoint_quality", None), default={"lanes": {}, "relays": {}}
        )

    def strategy_scorecards(self, runtime: Any) -> Dict[str, Any]:
        return self._snapshot(
            getattr(runtime, "_family_scorecards", None), default={"families": []}
        )

    def launch(self, runtime: Any) -> Dict[str, Any]:
        svc = getattr(runtime, "_launch_service", None)
        unavailable = unavailable_state("launch_service_unavailable")
        if getattr(runtime, "_family_hardening_service", None) is not None and hasattr(
            runtime, "family_hardening_state"
        ):
            try:
                unavailable["familyHardening"] = to_json_safe(runtime.family_hardening_state())
            except _STATE_SUMMARY_COMPONENT_FAILURES:
                unavailable["familyHardening"] = family_hardening_unavailable_summary()
        if svc is None or not hasattr(svc, "summary"):
            return unavailable
        try:
            return to_json_safe(svc.summary(runtime))
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            return unavailable

    def capital_engine(self, runtime: Any) -> Dict[str, Any]:
        treasury = getattr(runtime, "_treasury", None)
        if treasury is None:
            return {
                "capital_engine": {},
                "reinvestment_policy": {},
                "capital_efficiency_metrics": {},
            }
        try:
            snap = treasury.snapshot() if hasattr(treasury, "snapshot") else {}
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            snap = {}
        try:
            family_covariance = getattr(runtime, "_family_covariance", None)
            covariance_penalties = dict(
                family_covariance.penalties() if family_covariance is not None else {}
            )
        except _STATE_SUMMARY_COMPONENT_FAILURES:
            covariance_penalties = {}
        drawdown = self.drawdown(runtime)
        return to_json_safe(
            {
                "capital_engine": dict((snap or {}).get("capital_engine") or {}),
                "reinvestment_policy": dict((snap or {}).get("reinvestment_policy") or {}),
                "capital_efficiency_metrics": dict(
                    (snap or {}).get("capital_efficiency_metrics") or {}
                ),
                "covariance_penalties": covariance_penalties,
                "drawdown_state": drawdown,
            }
        )
