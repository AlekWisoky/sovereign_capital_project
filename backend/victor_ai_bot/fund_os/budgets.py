from __future__ import annotations

from typing import Any, Dict

from .fund_stage import default_fund_stages


def budget_ceilings(
    *, stage: str, nav_usd: float, family_targets: Dict[str, float] | None = None
) -> Dict[str, Any]:
    pol = default_fund_stages().get(str(stage), default_fund_stages()["internal_capital"])
    deployable = max(0.0, float(nav_usd) * float(pol.max_deployable_pct))
    fam_targets = dict(family_targets or {})
    family_budgets = {k: round(deployable * float(v), 2) for k, v in fam_targets.items()}
    return {
        "stage": pol.stage,
        "deployableCapitalUsd": round(deployable, 2),
        "experimentalCapitalUsd": round(float(nav_usd) * float(pol.experimental_capital_share), 2),
        "familyBudgetsUsd": family_budgets,
        "maxFamilyConcentration": float(pol.max_family_concentration),
        "maxEngineConcentration": float(pol.max_engine_concentration),
    }
