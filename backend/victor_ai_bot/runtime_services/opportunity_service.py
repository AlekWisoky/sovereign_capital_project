from __future__ import annotations

from typing import Any, Dict, Iterable, List

from victor_ai_bot.strategies import annotate_strategy_metadata
from victor_ai_bot.execution_capture.route_family_priors import default_route_family_priors


class OpportunityService:
    def annotate(self, opps: List[Any], *, regime: str) -> None:
        for opp in list(opps or []):
            try:
                if not isinstance(getattr(opp, "meta", None), dict):
                    opp.meta = {}
                meta = opp.meta
                strat = annotate_strategy_metadata(
                    strategy_name=str(getattr(opp, "strategy", "") or "flashloan_atomic"),
                    regime=str(regime),
                )
                meta["strategy_family"] = strat["family"]
                meta["strategy_meta"] = strat
                route_family = str(meta.get("route_family") or "")
                meta["route_family_priors"] = default_route_family_priors(route_family)
                if not bool(strat.get("regime_allowed", True)):
                    safety = (
                        dict(meta.get("safety") or {})
                        if isinstance(meta.get("safety"), dict)
                        else {}
                    )
                    safety["exec_ready"] = False
                    safety["reason"] = "strategy_regime_disallowed"
                    meta["safety"] = safety
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
