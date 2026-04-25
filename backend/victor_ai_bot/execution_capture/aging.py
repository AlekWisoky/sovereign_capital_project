from __future__ import annotations

import math
from typing import Any, Dict

_DEFAULT_HALF_LIFE_MS: Dict[str, int] = {
    "flashloan_atomic": 1800,
    "atomic_arb": 1800,
    "liquidation": 2500,
    "cross_cex_dex": 12000,
    "funding_arb": 6 * 60 * 60 * 1000,
    "cross_chain_arb": 12 * 60 * 1000,
    "mev_search": 1500,
}

_SAFE_HALF_LIFE_EXCEPTIONS = (TypeError, ValueError)


def half_life_ms(route_family: str, *, overrides: Dict[str, Any] | None = None) -> int:
    if overrides and route_family in overrides:
        try:
            return max(1, int(overrides[route_family]))
        except _SAFE_HALF_LIFE_EXCEPTIONS:
            pass
    return int(_DEFAULT_HALF_LIFE_MS.get(str(route_family or ""), 5000))


def aging_factor(
    *, route_family: str, age_ms: int, overrides: Dict[str, Any] | None = None
) -> float:
    age = max(0, int(age_ms or 0))
    hl = half_life_ms(str(route_family or ""), overrides=overrides)
    if age <= 0:
        return 1.0
    return max(0.05, min(1.0, math.exp(-float(age) / float(max(1, hl)))))
