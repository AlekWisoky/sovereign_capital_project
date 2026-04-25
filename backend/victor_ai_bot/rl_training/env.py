from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class TradingEnvState:
    realized_pnl: float = 0.0
    capital_efficiency: float = 0.0
    gas_cost: float = 0.0
    failures: int = 0
    stability: float = 0.5


class OfflineTradingEnv:
    def __init__(self):
        self.state = TradingEnvState()

    def reset(self) -> Dict[str, Any]:
        self.state = TradingEnvState()
        return self.observe()

    def observe(self) -> Dict[str, Any]:
        return self.state.__dict__.copy()

    def step(self, reward_components: Dict[str, Any]) -> Dict[str, Any]:
        self.state.realized_pnl += float(reward_components.get("realizedPnl", 0.0) or 0.0)
        self.state.capital_efficiency = float(
            reward_components.get("capitalEfficiency", self.state.capital_efficiency) or 0.0
        )
        self.state.gas_cost += float(reward_components.get("gasCost", 0.0) or 0.0)
        self.state.failures += int(reward_components.get("failures", 0) or 0)
        self.state.stability = float(
            reward_components.get("stability", self.state.stability) or 0.0
        )
        return self.observe()
