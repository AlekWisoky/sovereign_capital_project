from __future__ import annotations

from typing import Any, Dict, List

from .health_states import normalize_health_state
from .launch_modes import DEFAULT_ACTIVATION_ORDER
from .mandate_registry import fund_mandate_registry


class CapabilityHealthGraph:
    def __init__(
        self, *, profile: Dict[str, Any], readiness_items: List[Dict[str, Any]], stage: str
    ):
        self.profile = dict(profile or {})
        self.readiness_items = list(readiness_items or [])
        self.stage = str(stage or "internal_capital")

    def snapshot(self) -> Dict[str, Any]:
        mandates = dict((fund_mandate_registry().get("families") or {}))
        items: Dict[str, Any] = {}
        for family in DEFAULT_ACTIVATION_ORDER:
            readiness = next(
                (x for x in self.readiness_items if str(x.get("family") or "") == family), {}
            )
            mandate = dict(mandates.get(family) or {})
            items[family] = {
                "family": family,
                "state": normalize_health_state(
                    (self.profile.get("family_states") or {}).get(family)
                ),
                "active": family in list(self.profile.get("active_families") or []),
                "readiness_score": float(readiness.get("score") or 0.0),
                "status": str(readiness.get("status") or "blocked"),
                "blockers": list(readiness.get("blockers") or []),
                "stage_allowed": bool(readiness.get("stageAllowed")),
                "max_capital_pct": float(mandate.get("max_capital_pct") or 0.0),
                "strategy_class": str(mandate.get("class") or ""),
            }
        return {
            "stage": self.stage,
            "mode": str(self.profile.get("mode") or "V1_ONLY"),
            "families": items,
        }
