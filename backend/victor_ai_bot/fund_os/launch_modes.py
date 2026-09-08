from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List

from .health_states import HealthState


class LaunchMode(str, Enum):
    V1_ONLY = "V1_ONLY"
    V1_PLUS_STABLE_ALPHA = "V1_PLUS_STABLE_ALPHA"
    STAGED_MULTI_STRATEGY = "STAGED_MULTI_STRATEGY"
    FULL_MULTI_STRATEGY = "FULL_MULTI_STRATEGY"


DEFAULT_ACTIVATION_ORDER = [
    "flash_arb",
    "funding_arb",
    "cex_cex_arb",
    "liquidation_capture",
    "mev_search",
    "stat_arb",
    "volatility_market_making",
    "treasury_yield",
]


@dataclass
class LaunchProfile:
    mode: str = LaunchMode.V1_ONLY.value
    active_families: List[str] = field(default_factory=lambda: ["flash_arb"])
    requested_families: List[str] = field(default_factory=list)
    rollout_order: List[str] = field(default_factory=lambda: list(DEFAULT_ACTIVATION_ORDER))
    family_states: Dict[str, str] = field(
        default_factory=lambda: {
            family: (
                HealthState.LIVE.value if family == "flash_arb" else HealthState.OBSERVE_ONLY.value
            )
            for family in DEFAULT_ACTIVATION_ORDER
        }
    )
    history: List[Dict[str, Any]] = field(default_factory=list)
    exploration_budget: Dict[str, Any] = field(
        default_factory=lambda: {
            "max_trades": 3,
            "max_capital_usd": 25000.0,
            "max_cost_usd": 500.0,
            "used_trades": 0,
            "used_cost_usd": 0.0,
        }
    )
    last_recommendation: Dict[str, Any] = field(default_factory=dict)
    last_transition: Dict[str, Any] = field(default_factory=dict)
    updated_ts_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
