from __future__ import annotations

from typing import Any, Dict

from .profit_doctrine import objective_vector, profit_priority_score


def doctrine_snapshot() -> Dict[str, Any]:
    return {
        "optimizationObjectives": objective_vector(),
        "primaryObjective": "maximize_realized_pnl_subject_to_stability_and_capital_efficiency",
        "secondaryObjectives": [
            "minimize_execution_cost",
            "minimize_failed_execution",
            "maximize_capital_deployment_quality",
            "preserve_operator_trust",
        ],
    }


def evaluate_objective_fit(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return profit_priority_score(
        realized_pnl=float((metrics or {}).get("realizedPnl", 0.0) or 0.0),
        capital_efficiency=float((metrics or {}).get("capitalEfficiency", 0.0) or 0.0),
        execution_cost=float((metrics or {}).get("executionCost", 0.0) or 0.0),
        failure_rate=float((metrics or {}).get("failureRate", 0.0) or 0.0),
        stability_score=float((metrics or {}).get("stabilityScore", 0.0) or 0.0),
        competition_score=float((metrics or {}).get("competitionScore", 0.0) or 0.0),
    )
