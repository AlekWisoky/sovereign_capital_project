from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ProfitGoal:
    target_return_percentage: float = 0.0
    time_horizon_seconds: int = 7 * 24 * 3600
    risk_tolerance: str = "conservative"  # conservative|moderate|aggressive
    max_drawdown_pct: float = 10.0
    capital_commitment_pct: float = 25.0
    priority_weight: float = 1.0


@dataclass
class TreasuryConfig:
    enabled: bool = False
    mode: str = "observe"  # observe|suggest
    # Minimum liquidity buffer (fraction of estimated total)
    liquidity_min_buffer_pct: float = 25.0
    # Aggressiveness governance
    max_aggressiveness_without_approval: str = "HIGH"  # LOW|MODERATE|HIGH
    # Deterministic learning toggles
    rl_enabled: bool = True
    # Yield deployment (placeholder, gated)
    enable_yield_deployment: bool = False

    # Borrow scaling limits
    aggressiveness_max_borrow_mult: float = 3.0
    borrow_mult_min: float = 0.50
    # Logging
    data_dir: str = "backend/data"

    # Whether MAXIMUM aggressiveness is allowed without explicit config change
    allow_maximum: bool = False

    # If set, used for goal progress calculations (optional)
    estimated_capital_wei: int = 0

    # Primary goal object (preferred name)
    goal: ProfitGoal = field(default_factory=ProfitGoal)

    @property
    def profit_goal(self) -> ProfitGoal:
        """Backwards compatible alias."""
        return self.goal

    @property
    def min_liquidity_buffer_pct(self) -> float:  # backwards compatible alias
        return self.liquidity_min_buffer_pct

    @property
    def borrow_mult_cap(self) -> float:  # backwards compatible alias
        return self.aggressiveness_max_borrow_mult

    # extra knobs
    meta: Dict[str, Any] = field(default_factory=dict)
