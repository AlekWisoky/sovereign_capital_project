from __future__ import annotations

from typing import Any, Dict

from .budgets import budget_ceilings
from .mandate_registry import fund_mandate_registry
from .objectives import doctrine_snapshot, evaluate_objective_fit
from .permissions import operator_permissions
from ..alpha_platform.income_streams import rotation_plan


class FundMasterOrchestrator:
    def compose(
        self,
        *,
        stage: str,
        nav_usd: float,
        family_targets: Dict[str, float],
        income_metrics: Dict[str, Any],
        capital_metrics: Dict[str, Any],
        fund_health: Dict[str, Any],
    ) -> Dict[str, Any]:
        budgets = budget_ceilings(stage=stage, nav_usd=nav_usd, family_targets=family_targets)
        doctrine = doctrine_snapshot()
        fit = evaluate_objective_fit(
            {
                "realizedPnl": float((fund_health or {}).get("realizedPnlUsd", 0.0) or 0.0),
                "capitalEfficiency": float(
                    (capital_metrics or {}).get("failureAdjustedCapitalEfficiency", 0.0) or 0.0
                ),
                "executionCost": float((fund_health or {}).get("executionCostUsd", 0.0) or 0.0),
                "failureRate": float((fund_health or {}).get("failureRate", 0.0) or 0.0),
                "stabilityScore": float((fund_health or {}).get("stabilityScore", 0.5) or 0.0),
                "competitionScore": float((fund_health or {}).get("competitionScore", 0.5) or 0.0),
            }
        )
        rotation = rotation_plan(metrics=income_metrics)
        return {
            "profitDoctrine": doctrine,
            "objectiveFit": fit,
            "budgets": budgets,
            "mandates": fund_mandate_registry(),
            "permissions": operator_permissions(stage=stage),
            "incomeRotation": rotation,
        }
