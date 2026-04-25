from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class CapitalBuckets:
    execution_capital_pct: float
    reserve_capital_pct: float
    experimental_capital_pct: float
    drawdown_buffer_pct: float
    treasury_offramp_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_buckets(*, drawdown_pct: float, aggressiveness_level: str) -> CapitalBuckets:
    lvl = str(aggressiveness_level or "LOW").upper()
    execution = 0.48 if lvl == "LOW" else (0.58 if lvl == "MODERATE" else 0.66)
    reserve = 0.22 if lvl == "LOW" else (0.18 if lvl == "MODERATE" else 0.14)
    experimental = 0.08 if lvl == "LOW" else (0.10 if lvl == "MODERATE" else 0.12)
    drawdown = 0.14 if float(drawdown_pct) < 5.0 else 0.20
    treasury = max(0.04, 1.0 - (execution + reserve + experimental + drawdown))
    total = execution + reserve + experimental + drawdown + treasury
    execution, reserve, experimental, drawdown, treasury = [
        x / total for x in (execution, reserve, experimental, drawdown, treasury)
    ]
    return CapitalBuckets(execution, reserve, experimental, drawdown, treasury)
