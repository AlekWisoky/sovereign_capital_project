from __future__ import annotations

from typing import Any, Dict


def risk_controls(*, risk_score: float, fund_stage: Dict[str, Any]) -> Dict[str, Any]:
    max_dep = float((fund_stage or {}).get("max_deployable_pct") or 0.35)
    experimental = float((fund_stage or {}).get("experimental_capital_share") or 0.12)
    if risk_score >= 0.80:
        return {"deployableScale": 0.55, "experimentalScale": 0.30, "reason": "severe_risk"}
    if risk_score >= 0.60:
        return {"deployableScale": 0.75, "experimentalScale": 0.60, "reason": "elevated_risk"}
    return {
        "deployableScale": 1.0,
        "experimentalScale": 1.0,
        "reason": "normal",
        "stageDeployablePct": max_dep,
        "stageExperimentalPct": experimental,
    }
