from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class InventoryTargets:
    """Target capital distribution (percentages 0..1)."""

    on_chain: float
    cex_spot: float
    cex_futures: float
    stable_reserves: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "on_chain": float(self.on_chain),
            "cex_spot": float(self.cex_spot),
            "cex_futures": float(self.cex_futures),
            "stable_reserves": float(self.stable_reserves),
        }


class InventoryBalancer:
    """Advisory inventory/capital balancer.

    This is a *planning* module used by the Treasury layer:
      - produces target allocations across buckets
      - never executes transfers
      - deterministic for a given input state

    Buckets are conceptual:
      - on_chain: liquidity for atomic flash + DEX interactions
      - cex_spot: spot inventory for cross-exchange/spot arb
      - cex_futures: margin/collateral for perp hedges/funding arb
      - stable_reserves: safety buffer / liquidity buffer / idle cash
    """

    def __init__(self, *, min_stable_reserve: float = 0.15):
        self.min_stable_reserve = float(min_stable_reserve)

    def compute_targets(
        self,
        *,
        volatility_regime: str,
        aggressiveness_level: str,
        liquidity_buffer: float,
    ) -> Dict[str, Any]:
        vr = str(volatility_regime or "unknown").lower()
        ag = str(aggressiveness_level or "LOW").upper()

        # Base heuristic
        on_chain = 0.35
        cex_spot = 0.20
        cex_fut = 0.20
        stable = 0.25

        # Volatility adjustment
        if "high" in vr or "risk" in vr:
            stable += 0.10
            on_chain -= 0.05
            cex_spot -= 0.03
            cex_fut -= 0.02

        # Aggressiveness adjustment
        if ag in {"HIGH", "MAXIMUM"}:
            on_chain += 0.08
            cex_fut += 0.05
            stable -= 0.10
            cex_spot -= 0.03
        elif ag == "MODERATE":
            on_chain += 0.04
            cex_fut += 0.02
            stable -= 0.05
            cex_spot -= 0.01

        # Liquidity buffer requirement (never go below)
        stable = max(stable, float(self.min_stable_reserve), float(liquidity_buffer))

        # Normalize
        total = on_chain + cex_spot + cex_fut + stable
        if total <= 1e-9:
            total = 1.0
        on_chain /= total
        cex_spot /= total
        cex_fut /= total
        stable /= total

        targets = InventoryTargets(
            on_chain=on_chain, cex_spot=cex_spot, cex_futures=cex_fut, stable_reserves=stable
        )

        notes = []
        if stable <= float(self.min_stable_reserve) + 1e-9:
            notes.append("stable_reserve_floor")
        if "high" in vr:
            notes.append("volatility_regime_high")
        if ag in {"HIGH", "MAXIMUM"}:
            notes.append("aggressive_allocation")

        return {
            "targets": targets.as_dict(),
            "inputs": {
                "volatility_regime": str(volatility_regime),
                "aggressiveness_level": str(aggressiveness_level),
                "liquidity_buffer": float(liquidity_buffer),
            },
            "notes": notes,
        }
