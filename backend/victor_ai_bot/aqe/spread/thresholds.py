from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ThresholdConfig:
    base_alpha: float = 0.10
    high_vol_mult: float = 1.25
    stress_mult: float = 1.35
    low_liquidity_mult: float = 1.20
    aggressive_mult: float = 0.85  # lowers threshold in aggressive mode (still gated by safety)


class AdaptiveThresholds:
    """Adaptive threshold helper.

    Thresholds are designed to be deterministic:
    - depends only on provided inputs
    - no randomness
    """

    def __init__(self, *, cfg: ThresholdConfig | None = None):
        self.cfg = cfg or ThresholdConfig()

    def dynamic_threshold(self, *, regime: str, stress: Dict[str, Any] | None = None, aggressiveness: str = "LOW") -> float:
        thr = float(self.cfg.base_alpha)
        r = str(regime or "").lower()
        s = dict(stress or {})

        if r in {"high_vol", "risk_off", "volatile", "panic"}:
            thr *= float(self.cfg.high_vol_mult)
        if bool(s.get("stress", False)) or float(s.get("mev_risk", 0.0) or 0.0) > 0.75:
            thr *= float(self.cfg.stress_mult)
        if float(s.get("liquidity", 1.0) or 1.0) < 0.35:
            thr *= float(self.cfg.low_liquidity_mult)

        a = str(aggressiveness or "LOW").upper()
        if a in {"HIGH", "MAXIMUM"}:
            thr *= float(self.cfg.aggressive_mult)

        return float(max(0.02, min(2.0, thr)))