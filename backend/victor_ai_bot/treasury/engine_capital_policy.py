from __future__ import annotations

from typing import Any, Dict

from victor_ai_bot.capital_family_policy import resolve_family_capital_limit
from victor_ai_bot.strategies.engine_family_bindings import family_for_engine


def engine_capital_limits(
    *, engine_type: str, treasury_state: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    treasury_state = dict(treasury_state or {})
    capital_engine = dict(treasury_state.get("capital_engine") or {})
    fam = family_for_engine(engine_type)
    deployable_wei = int(capital_engine.get("deployable_bankroll_wei") or 0)
    family_limit = resolve_family_capital_limit(capital_engine=capital_engine, family=fam)
    family_cap_wei = int(family_limit.get("family_allocation_wei") or 0)
    return {
        "engine_type": str(engine_type),
        "strategy_family": fam,
        "deployable_capital_usd": round(deployable_wei / 1e18, 6),
        "family_capital_usd": round(family_cap_wei / 1e18, 6),
        "family_target": float(family_limit.get("family_target") or 0.0),
        "target_known": bool(family_limit.get("target_known", False)),
        "resolved_target_key": str(family_limit.get("resolved_target_key") or ""),
        "resolved_allocation_key": str(family_limit.get("resolved_allocation_key") or ""),
    }
