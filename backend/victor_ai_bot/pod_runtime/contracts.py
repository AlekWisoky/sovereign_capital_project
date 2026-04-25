from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class StrategyPodContract:
    pod_id: str
    family: str
    health: str
    budget_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
