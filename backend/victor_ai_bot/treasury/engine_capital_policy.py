from __future__ import annotations

import math
from typing import Any, Dict

from victor_ai_bot.capital_family_policy import resolve_family_capital_limit
from victor_ai_bot.strategies.engine_family_bindings import family_for_engine


def _explicit_usd(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0.0:
        return None
    return number


def engine_capital_limits(
    *, engine_type: str, treasury_state: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Expose engine capital limits without inventing USD from raw asset units."""
    treasury_state = dict(treasury_state or {})
    capital_engine = dict(treasury_state.get("capital_engine") or {})
    fam = family_for_engine(engine_type)
    family_limit = resolve_family_capital_limit(capital_engine=capital_engine, family=fam)
    resolved_allocation_key = str(family_limit.get("resolved_allocation_key") or fam)

    deployable_usd = _explicit_usd(capital_engine.get("deployable_usd"))
    family_allocations_usd = dict(capital_engine.get("family_allocations_usd") or {})
    family_capital_usd = _explicit_usd(
        family_allocations_usd.get(resolved_allocation_key)
        if resolved_allocation_key in family_allocations_usd
        else family_allocations_usd.get(fam)
    )

    return {
        "engine_type": str(engine_type),
        "strategy_family": fam,
        "deployable_capital_usd": deployable_usd if deployable_usd is not None else 0.0,
        "family_capital_usd": family_capital_usd if family_capital_usd is not None else 0.0,
        "economic_value_source": (
            "capital_engine.deployable_usd"
            if deployable_usd is not None
            else "unavailable"
        ),
        "family_economic_value_source": (
            "capital_engine.family_allocations_usd"
            if family_capital_usd is not None
            else "unavailable"
        ),
        "target_known": bool(family_limit.get("target_known", False)),
        "family_target": float(family_limit.get("family_target") or 0.0),
        "resolved_target_key": str(family_limit.get("resolved_target_key") or ""),
        "resolved_allocation_key": resolved_allocation_key,
    }
