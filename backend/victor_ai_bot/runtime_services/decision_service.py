from __future__ import annotations

from typing import Any, Dict


class DecisionService:
    def execution_context(
        self,
        *,
        opp: Any,
        capture: Dict[str, Any],
        strategy_family: str,
        capital_limits: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "opportunity_id": str(getattr(opp, "id", "") or ""),
            "route_id": str(getattr(opp, "route_id", "") or ""),
            "strategy_family": str(strategy_family or "flashloan_atomic"),
            "capture": dict(capture or {}),
            "capital_limits": dict(capital_limits or {}),
        }
