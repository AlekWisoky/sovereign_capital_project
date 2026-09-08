from __future__ import annotations

from typing import Any, Dict

from .family_hardening_service import FamilyHardeningService as _FamilyHardeningService


class RuntimeFamilyHardeningService(_FamilyHardeningService):
    """Runtime-safe family hardening view that avoids launch/fund summary recursion."""

    @staticmethod
    def _context(runtime: Any) -> Dict[str, Any]:
        fund_summary = (
            runtime.fund_summary_state() if hasattr(runtime, "fund_summary_state") else {}
        )
        return {
            "stage": str(
                (
                    (fund_summary.get("health") or fund_summary).get("fundStage")
                    if isinstance(fund_summary, dict)
                    else "internal_capital"
                )
                or "internal_capital"
            ),
            "scorecards": (
                runtime.strategy_scorecards_state()
                if hasattr(runtime, "strategy_scorecards_state")
                else {"families": []}
            ),
            "engine_state": runtime.engine_state() if hasattr(runtime, "engine_state") else {},
            "telemetry": (
                runtime.telemetry_summary() if hasattr(runtime, "telemetry_summary") else {}
            ),
            "calibration": (
                runtime.execution_calibration_state()
                if hasattr(runtime, "execution_calibration_state")
                else {}
            ),
            "fund_summary": (
                fund_summary.get("health")
                if isinstance(fund_summary, dict) and isinstance(fund_summary.get("health"), dict)
                else fund_summary
            ),
            "active_families": list(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "active_families",
                    [],
                )
                or []
            ),
            "family_states": dict(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "family_states",
                    {},
                )
                or {}
            ),
            "exploration_budget": dict(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "exploration_budget",
                    {},
                )
                or {}
            ),
            "capital_state": (
                runtime.capital_engine_state() if hasattr(runtime, "capital_engine_state") else {}
            ),
        }
