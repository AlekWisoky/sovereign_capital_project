from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from victor_ai_bot.capital_family_policy import resolve_family_capital_limit


@dataclass(frozen=True)
class CapitalDecision:
    admitted: bool
    reason: str
    limits: Dict[str, Any]


class TreasuryService:
    def state(self, runtime: Any) -> Dict[str, Any]:
        return runtime.capital_engine_state()

    def check_family_admission(
        self, *, capital_state: Dict[str, Any], strategy_family: str, expected_value: float
    ) -> CapitalDecision:
        family_limit = resolve_family_capital_limit(
            capital_engine=(capital_state.get("capital_engine") or {}),
            family=str(strategy_family),
        )
        target = float(family_limit.get("family_target") or 0.0)
        if expected_value > 0.0 and not bool(family_limit.get("target_known", False)):
            return CapitalDecision(False, "family_cap_unknown", dict(family_limit))
        if target <= 0.0 and expected_value > 0.0:
            return CapitalDecision(False, "family_cap_zero", dict(family_limit))
        return CapitalDecision(True, "ok", dict(family_limit))
