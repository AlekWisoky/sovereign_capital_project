from __future__ import annotations

from typing import Dict

from .families import StrategyFamily


def strategy_regime_fit(family: StrategyFamily, regime: str) -> float:
    r = str(regime or "balanced")
    if r in set(family.disallowed_regimes):
        return 0.0
    if r in set(family.preferred_regimes):
        return 1.0
    return 0.55
