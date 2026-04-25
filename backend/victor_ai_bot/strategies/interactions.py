from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

from .interaction_model import interaction_risk


def interaction_conflicts(
    *, used_pools: Iterable[str], strategy_family: str, other_families: Iterable[str]
) -> Dict[str, Any]:
    pools = set(str(x) for x in list(used_pools or []))
    families = set(str(x) for x in list(other_families or []))
    duplicated_liquidity = bool(pools)
    correlated_failure = bool(strategy_family in families)
    cannibalization = bool(strategy_family in families and len(pools) > 0)
    model = interaction_risk(
        family_a=str(strategy_family),
        family_b=str(next(iter(families)) if families else ""),
        tokens_a=list(pools),
        tokens_b=list(pools),
        venues_a=[],
        venues_b=[],
        chains_a=[],
        chains_b=[],
        shared_failure_mode=correlated_failure,
    )
    return {
        "duplicated_liquidity_usage": duplicated_liquidity,
        "correlated_failure": correlated_failure,
        "strategy_cannibalization": cannibalization,
        "interaction_risk": float(model.get("interaction_risk") or 0.0),
        "allow": not (correlated_failure and cannibalization)
        and float(model.get("interaction_risk") or 0.0) < 0.85,
    }
