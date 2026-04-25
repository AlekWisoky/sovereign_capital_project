from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class LearningPolicy:
    min_live_observations: int = 8
    safe_exploration_capital_share: float = 0.015
    safe_exploration_daily_cost_usd: float = 15.0
    quarantine_failure_threshold: int = 3
    quarantine_penalty: float = 0.35
    confidence_size_floor: float = 0.45
    confidence_size_cap: float = 1.15

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
