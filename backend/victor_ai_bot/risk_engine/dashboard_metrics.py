from __future__ import annotations

from typing import Any, Dict


def cio_dashboard_metrics(
    *,
    capital: Dict[str, Any],
    risk: Dict[str, Any],
    alpha: Dict[str, Any],
    research: Dict[str, Any],
    internal_prime: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    cap_eff = dict((capital or {}).get("capital_efficiency_metrics") or {})
    risk_score = float((risk or {}).get("riskScore") or 0.0)
    util = float(cap_eff.get("utilizationRate") or 0.0)
    drawdown = float((risk or {}).get("drawdownPct") or 0.0)
    alpha_eng = list((alpha or {}).get("scorecards", {}).get("engines") or [])
    health = (
        float(
            sum(float((x or {}).get("stability") or 0.0) for x in alpha_eng)
            / max(1, len(alpha_eng))
        )
        if alpha_eng
        else 0.0
    )
    return {
        "sharpeProxy": round(
            float((cap_eff.get("returnOnDeployedCapital") or 0.0))
            * max(0.1, 1.0 - drawdown / 20.0),
            6,
        ),
        "varProxy": round(risk_score * 0.7 + drawdown * 0.3, 6),
        "capitalUtilization": util,
        "familyHealth": round(health, 6),
        "researchHitRate": float(
            (research or {}).get("throughput", {}).get("researchHitRate") or 0.0
        ),
        "primeUtilization": float((internal_prime or {}).get("utilization") or 0.0),
    }
