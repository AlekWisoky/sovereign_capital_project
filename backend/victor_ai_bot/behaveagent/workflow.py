from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from victor_ai_bot.determinism import stable_hash_int


STRATEGY_TYPES = [
    "dex_flash_2leg",
    "dex_flash_3leg",
    "cex_spot_spot",
    "spot_futures",
    "futures_futures",
    "funding_arb",
    "cex_dex",
    "cross_chain_scaffold",
]


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

@dataclass
class StrategyOverlay:
    regime: str
    confidence: float
    objectives: Dict[str, Any]
    priority: Dict[str, float]
    intent_vector: Dict[str, Any]


def generate_strategy_priority(
    *,
    regime: str,
    confidence: float,
    aggressiveness: str,
    profit_goal: Dict[str, Any] | None = None,
    seed: str = "",
) -> StrategyOverlay:
    """Generate strategy priority matrix + intent vector.

    Deterministic: for the same inputs, output is identical.
    """

    r = str(regime or "unknown").lower()
    a = str(aggressiveness or "LOW").upper()
    goal = dict(profit_goal or {})

    # Baseline weights
    w = {k: 1.0 for k in STRATEGY_TYPES}

    # Regime adjustments (conservative defaults)
    if r in {"mev_stress", "gas_spike"}:
        w["dex_flash_3leg"] *= 0.70
        w["dex_flash_2leg"] *= 0.85
        w["cex_spot_spot"] *= 0.95
        w["spot_futures"] *= 0.90
    if r in {"high_vol", "risk_off"}:
        w["funding_arb"] *= 1.10
        w["spot_futures"] *= 1.05
        w["dex_flash_3leg"] *= 0.85

    # Aggressiveness adjustments
    if a in {"HIGH", "MAXIMUM"}:
        w["dex_flash_2leg"] *= 1.10
        w["dex_flash_3leg"] *= 1.05
        w["cex_dex"] *= 1.10
    else:
        w["dex_flash_3leg"] *= 0.95

    # Profit goal urgency (if provided)
    urgency = float(goal.get("urgency_factor", 0.0) or 0.0)
    if urgency > 0.5:
        w["dex_flash_2leg"] *= 1.08
        w["spot_futures"] *= 1.06
    if urgency > 1.0:
        w["dex_flash_3leg"] *= 1.05
        w["futures_futures"] *= 1.05

    # Deterministic tie-breaker: small stable perturbation
    for k in list(w.keys()):
        bump = (stable_hash_int(f"prio:{seed}:{r}:{a}:{k}", modulo=10_000) / 10_000.0) * 1e-3
        w[k] = float(w[k]) + float(bump)

    # Normalize to 0..1
    mx = max(w.values()) if w else 1.0
    pr = {k: float(_clip(float(v) / float(mx), 0.0, 1.0)) for k, v in w.items()}

    objectives = {
        "regime": r,
        "risk_posture": "conservative" if a in {"LOW"} else ("moderate" if a in {"MODERATE"} else "aggressive"),
        "profit_goal": goal,
    }

    intent_vector = {
        "explore": bool(confidence < 0.55),
        "explore_cap_fraction": float(goal.get("exploration_cap_fraction", 0.10) or 0.10),
        "aggressiveness": a,
        "seed": str(seed),
    }

    return StrategyOverlay(regime=r, confidence=float(_clip(confidence, 0.0, 1.0)), objectives=objectives, priority=pr, intent_vector=intent_vector)
