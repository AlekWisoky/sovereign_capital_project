from __future__ import annotations

from typing import Any, Dict

from .auxiliary_state_service import AuxiliaryStateService
from .summary_read_contract import build_summary_read_contract
from .capital_truth_read_context import build_capital_truth_read_context


class AnalyticsService:
    def __init__(self, *, auxiliary_state: AuxiliaryStateService | None = None) -> None:
        self.auxiliary_state = auxiliary_state or AuxiliaryStateService()

    def system_summary(self, runtime: Any) -> Dict[str, Any]:
        try:
            fund_summary = (
                runtime.fund_summary_state() if hasattr(runtime, "fund_summary_state") else {}
            )
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            fund_summary = {}
        health = (
            dict((fund_summary.get("health") or fund_summary))
            if isinstance(fund_summary, dict)
            else {}
        )
        capital_context = build_capital_truth_read_context(
            runtime,
            auxiliary_state=self.auxiliary_state,
            fund_summary=health,
            include_operator_projection=False,
        )
        capital_truth = capital_context.capital_truth
        capital_truth_health = dict(capital_context.capital_truth_health or {})
        capital_surface = dict(capital_context.capital_surface or {})
        payload = {
            "telemetry": (
                runtime.telemetry_summary() if hasattr(runtime, "telemetry_summary") else {}
            ),
            "calibration": (
                runtime.execution_calibration_state()
                if hasattr(runtime, "execution_calibration_state")
                else {}
            ),
            "agents": runtime.agent_hub_state() if hasattr(runtime, "agent_hub_state") else {},
            "capital": (
                runtime.capital_engine_state() if hasattr(runtime, "capital_engine_state") else {}
            ),
            **capital_surface,
            "capitalContractVersion": capital_truth.capital_contract.get("contractVersion", ""),
            "capitalPolicyVersion": capital_truth.capital_policy.get("contractVersion", ""),
            "treasuryState": self.auxiliary_state.treasury_state(
                runtime, capital_truth=capital_truth
            ),
            "endpointQuality": (
                runtime.endpoint_quality_state()
                if hasattr(runtime, "endpoint_quality_state")
                else {}
            ),
            "drawdown": runtime.drawdown_state() if hasattr(runtime, "drawdown_state") else {},
            "killSwitch": (
                runtime.kill_switch_state() if hasattr(runtime, "kill_switch_state") else {}
            ),
            "endpointUniverse": (
                runtime.endpoint_universe_state()
                if hasattr(runtime, "endpoint_universe_state")
                else {}
            ),
            "venueScorecards": (
                runtime.venue_scorecards_state()
                if hasattr(runtime, "venue_scorecards_state")
                else {}
            ),
            "routeQuality": (
                runtime.route_quality_state() if hasattr(runtime, "route_quality_state") else {}
            ),
            "liveExecution": (
                runtime.execution_live_state()
                if hasattr(runtime, "execution_live_state")
                else {"items": []}
            ),
        }
        payload["summaryContract"] = build_summary_read_contract(
            family="analytics_system",
            payload=payload,
            capital_contract=capital_truth.capital_contract,
            capital_policy=capital_truth.capital_policy,
            source_contracts={
                "telemetry": (payload.get("telemetry") or {}),
                "capitalTruthHealth": capital_truth_health,
            },
            phase="analytics_system_summary",
            read_model="analytics_system_summary_projection_v1",
        )
        return payload
