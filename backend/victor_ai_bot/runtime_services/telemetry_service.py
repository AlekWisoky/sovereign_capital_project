from __future__ import annotations

import time
from typing import Any, Dict

from victor_ai_bot.telemetry.events import TelemetryEvent
from victor_ai_bot.telemetry.feedback import compute_feedback
from victor_ai_bot.telemetry.store import TelemetryStore

from .control_state import unavailable_state
from .summary_read_contract import build_summary_read_contract


class TelemetryService:
    def __init__(self, *, store: TelemetryStore):
        self.store = store

    @staticmethod
    def _service_unavailable(reason_code: str) -> Dict[str, Any]:
        return unavailable_state(str(reason_code))

    def _summarize_or_unavailable(
        self, runtime: Any, attr: str, reason_code: str
    ) -> Dict[str, Any]:
        svc = getattr(runtime, attr, None)
        if svc is None or not hasattr(svc, "summarize"):
            return self._service_unavailable(reason_code)
        try:
            payload = svc.summarize(runtime)
        except (AttributeError, KeyError, TypeError, ValueError):
            return self._service_unavailable(reason_code)
        return payload if isinstance(payload, dict) else self._service_unavailable(reason_code)

    def _wealth_goal_health(self, runtime: Any) -> Dict[str, Any]:
        svc = getattr(runtime, "_wealth_goal_service", None)
        if svc is None or not hasattr(svc, "state"):
            return self._service_unavailable("wealth_goal_service_unavailable")
        try:
            payload = svc.state(runtime)
        except (AttributeError, KeyError, TypeError, ValueError):
            return self._service_unavailable("wealth_goal_service_unavailable")
        if not isinstance(payload, dict):
            return self._service_unavailable("wealth_goal_service_unavailable")
        state = payload.get("state")
        if isinstance(state, dict):
            out = dict(state)
            out.setdefault("ok", bool(payload.get("ok", True)))
            return out
        reason_code = str(
            payload.get("reason_code")
            or payload.get("error")
            or payload.get("reason")
            or "wealth_goal_service_unavailable"
        )
        return unavailable_state(
            reason_code,
            include_reason=("reason" in payload) or ("error" not in payload),
            include_error=("error" in payload),
        )

    def record(self, event_type: str, payload: Dict[str, Any], *, chain: str) -> None:
        ev = TelemetryEvent(
            event_type=str(event_type),
            chain=str(chain),
            ts_ms=int(time.time() * 1000),
            payload=dict(payload or {}),
        )
        self.store.append(ev)

    def record_decision(
        self,
        *,
        route_family: str,
        strategy_family: str,
        projected_realized_edge_usd: float,
        actual_realized_edge_usd: float,
        ok: bool,
        dropped: bool,
        chain: str,
        reward_trace: Dict[str, Any],
        false_drop: float = 0.0,
        decision_reason: str = "",
    ) -> None:
        self.record(
            "decision",
            {
                "route_family": str(route_family or ""),
                "strategy_family": str(strategy_family or ""),
                "projected_realized_edge_usd": float(projected_realized_edge_usd or 0.0),
                "actual_realized_edge_usd": float(actual_realized_edge_usd or 0.0),
                "dropped": bool(dropped),
                "ok": bool(ok),
                "false_drop": float(false_drop or 0.0),
                "reward_trace": dict(reward_trace or {}),
                "reward": float((reward_trace or {}).get("reward") or 0.0),
                "decision_reason": str(decision_reason or ""),
            },
            chain=chain,
        )

    def record_outcome(
        self,
        *,
        route_family: str,
        strategy_family: str,
        projected_realized_edge_usd: float,
        actual_realized_edge_usd: float,
        projected_gross_edge_usd: float,
        ok: bool,
        lane: str,
        chain: str,
        reward_trace: Dict[str, Any],
        false_admission: float = 0.0,
    ) -> None:
        self.record(
            "outcome",
            {
                "route_family": str(route_family or ""),
                "strategy_family": str(strategy_family or ""),
                "projected_realized_edge_usd": float(projected_realized_edge_usd or 0.0),
                "actual_realized_edge_usd": float(actual_realized_edge_usd or 0.0),
                "projected_gross_edge_usd": float(projected_gross_edge_usd or 0.0),
                "ok": bool(ok),
                "lane": str(lane or ""),
                "dropped": False,
                "false_admission": float(false_admission or 0.0),
                "false_drop": 0.0,
                "reward_trace": dict(reward_trace or {}),
                "reward": float((reward_trace or {}).get("reward") or 0.0),
            },
            chain=chain,
        )

    def summary(self) -> Dict[str, Any]:
        payload = dict(compute_feedback(self.store.tail(limit=1000)) or {})
        payload["summaryContract"] = build_summary_read_contract(
            family="telemetry",
            payload=payload,
            phase="telemetry_summary",
            read_model="telemetry_summary_projection_v1",
        )
        return payload

    def service_summary(self, runtime: Any) -> Dict[str, Any]:
        tail = self.store.tail(limit=200)
        live = (
            runtime.execution_live_state()
            if hasattr(runtime, "execution_live_state")
            else {"items": []}
        )
        payload = {
            "ok": True,
            "tailCount": len(tail),
            "feedback": compute_feedback(tail),
            "liveItems": (
                len(list((live or {}).get("items") or [])) if isinstance(live, dict) else 0
            ),
        }
        payload["summaryContract"] = build_summary_read_contract(
            family="telemetry_service",
            payload=payload,
            phase="telemetry_service_summary",
            read_model="telemetry_service_summary_projection_v1",
        )
        return payload

    def service_health(self, runtime: Any) -> Dict[str, Any]:
        admission = self._summarize_or_unavailable(
            runtime, "_admission_service", "admission_service_unavailable"
        )
        execution = self._summarize_or_unavailable(
            runtime, "_execution_service", "execution_service_unavailable"
        )
        receipt = self._summarize_or_unavailable(
            runtime, "_receipt_service", "receipt_service_unavailable"
        )
        telemetry = self.service_summary(runtime)
        wealth_goal = self._wealth_goal_health(runtime)
        return {
            "admission": admission,
            "execution": execution,
            "receipt": receipt,
            "telemetry": telemetry,
            "wealthGoal": wealth_goal,
        }
