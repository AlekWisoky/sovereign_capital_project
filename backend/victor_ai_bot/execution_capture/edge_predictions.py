from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class EdgePrediction:
    success_probability: float
    competition_probability: float
    quality_adjustment_factor: float
    freshness_decay_factor: float
    reliability_factor: float
    expected_slippage_bias: float = 0.0
    failure_mode_risk: float = 0.0
    route_fragility: float = 0.0
    data_sufficiency: float = 0.0
    reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
