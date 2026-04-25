from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StrategyProfile:
    """A bounded strategy preset (config patch).

    Safety:
      - Never enables auto-trading by default.
      - Designed to be applied as a *patch* over an existing YAML config.
    """
    name: str
    tier: str  # basic|advanced
    description: str
    patch: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "tier": self.tier, "description": self.description, "patch": self.patch}


# --- Default strategy set ---
# NOTE: these are templates; profitability depends on market conditions and execution quality.

STRATEGY_LIBRARY: List[StrategyProfile] = [
    StrategyProfile(
        name="defi_triangular_conservative",
        tier="basic",
        description="Conservative DeFi triangular scanning with strict safety gates (dry-run default).",
        patch={
            "flags": {"enable_three_leg_loops": True, "enable_two_leg_loops": True, "enable_discovery": True},
            "safety": {"slippage_bps": 35, "minProfitBps": 8, "require_estimate_gas": True, "require_simulation": True},
            "execution": {"gas_mode": "standard", "max_submit_per_block": 1},
        },
    ),
    StrategyProfile(
        name="defi_triangular_fast_gas",
        tier="advanced",
        description="Aggressive gas posture for very high-margin opportunities (keeps simulation gate).",
        patch={
            "safety": {"slippage_bps": 40, "minProfitBps": 10, "require_simulation": True},
            "execution": {"gas_mode": "fast"},
        },
    ),
    StrategyProfile(
        name="funding_harvest_observe",
        tier="basic",
        description="Observe-only funding-rate harvesting signals (CEX adapters enabled; no execution).",
        patch={
            "execution": {"arbitrage": {"enabled": True, "mode": "observe", "allow_execution": False, "leverage": 1.0}},
        },
    ),
    StrategyProfile(
        name="cross_venue_spread_observe",
        tier="advanced",
        description="Observe-only cross-venue spread screener tuned for large, liquid pairs.",
        patch={
            "execution": {"arbitrage": {"enabled": True, "mode": "observe", "min_spread_bps": 10, "max_notional_usd": 10000.0}},
        },
    ),
    StrategyProfile(
        name="mev_defensive_private",
        tier="basic",
        description="Defensive MEV monitoring + prefer private/protected submission when risk is high.",
        patch={
            "execution": {"mev": {"enabled": True, "mode": "defensive", "refuse_public_send_on_high_risk": True}},
        },
    ),
]
