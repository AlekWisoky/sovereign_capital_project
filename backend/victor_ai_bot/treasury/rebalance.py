from __future__ import annotations

from typing import Any, Dict


def rebalance_plan(
    *, current_weights: Dict[str, float], target_weights: Dict[str, float], nav_usd: float
) -> Dict[str, Any]:
    families = sorted(set(current_weights) | set(target_weights))
    changes = {}
    for fam in families:
        delta = float(target_weights.get(fam, 0.0)) - float(current_weights.get(fam, 0.0))
        changes[fam] = {
            "deltaWeight": round(delta, 6),
            "deltaCapitalUsd": round(delta * float(nav_usd), 2),
        }
    return {"changes": changes}
