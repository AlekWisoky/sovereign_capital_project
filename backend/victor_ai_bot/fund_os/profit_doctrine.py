from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProfitDoctrine:
    realized_pnl_weight: float = 1.0
    capital_efficiency_weight: float = 0.7
    execution_cost_weight: float = -0.6
    failure_penalty_weight: float = -0.9
    stability_weight: float = 0.8
    competition_survival_weight: float = 0.7
    required_reason_codes: tuple[str, ...] = (
        "realized_edge",
        "capital_efficiency",
        "cost",
        "failure_penalty",
        "stability",
        "competition",
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_profit_doctrine() -> ProfitDoctrine:
    return ProfitDoctrine()


def objective_vector() -> Dict[str, float]:
    d = default_profit_doctrine()
    return {
        "realized_pnl": d.realized_pnl_weight,
        "capital_efficiency": d.capital_efficiency_weight,
        "execution_cost": d.execution_cost_weight,
        "failure_penalty": d.failure_penalty_weight,
        "stability": d.stability_weight,
        "competition_survival": d.competition_survival_weight,
    }


def profit_priority_score(
    *,
    realized_pnl: float,
    capital_efficiency: float,
    execution_cost: float,
    failure_rate: float,
    stability_score: float,
    competition_score: float,
) -> Dict[str, Any]:
    d = default_profit_doctrine()
    contributions = {
        "realized_edge": float(realized_pnl) * d.realized_pnl_weight,
        "capital_efficiency": float(capital_efficiency) * d.capital_efficiency_weight,
        "cost": float(execution_cost) * d.execution_cost_weight,
        "failure_penalty": float(failure_rate) * d.failure_penalty_weight,
        "stability": float(stability_score) * d.stability_weight,
        "competition": float(competition_score) * d.competition_survival_weight,
    }
    total = sum(contributions.values())
    reason_codes: List[str] = []
    for k, v in contributions.items():
        if k in {"cost", "failure_penalty"} and v < -0.25:
            reason_codes.append(f"{k}_high")
        elif k in {"realized_edge", "capital_efficiency", "stability", "competition"} and v > 0.25:
            reason_codes.append(f"{k}_strong")
    if total < 0:
        reason_codes.append("profit_doctrine_negative")
    return {
        "score": round(float(total), 6),
        "reasonCodes": reason_codes,
        "contributions": {k: round(float(v), 6) for k, v in contributions.items()},
    }
