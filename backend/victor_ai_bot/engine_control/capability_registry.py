from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .models import EngineCapability


@dataclass
class EngineCapabilityRegistry:
    items: Dict[str, EngineCapability]

    def get(self, engine_type: str) -> EngineCapability:
        return self.items[str(engine_type)]

    def snapshot(self):
        return {k: v.to_dict() for k, v in self.items.items()}


def default_engine_capability_registry() -> EngineCapabilityRegistry:
    items = {
        "cross_cex_dex": EngineCapability(
            "cross_cex_dex",
            "beta",
            ["observe_only", "paper", "capped_live"],
            0.18,
            0.70,
            "protected_or_private",
            0.60,
            20,
            ["paper", "live"],
        ),
        "funding_arb": EngineCapability(
            "funding_arb",
            "beta",
            ["observe_only", "paper", "shadow_live", "capped_live"],
            0.22,
            0.85,
            "protected",
            0.62,
            30,
            ["paper", "live"],
        ),
        "cross_chain_arb": EngineCapability(
            "cross_chain_arb",
            "alpha",
            ["observe_only", "paper", "capped_live"],
            0.08,
            0.35,
            "observe_or_private",
            0.72,
            50,
            ["paper"],
        ),
        "mev_search": EngineCapability(
            "mev_search",
            "beta",
            ["observe_only", "paper", "capped_live"],
            0.10,
            0.55,
            "private_only",
            0.68,
            25,
            ["paper", "live"],
        ),
        "auto_strategy_generator": EngineCapability(
            "auto_strategy_generator",
            "beta",
            ["sandbox", "paper", "shadow_live"],
            0.05,
            0.25,
            "observe_only",
            0.66,
            40,
            ["paper"],
        ),
    }
    return EngineCapabilityRegistry(items=items)
