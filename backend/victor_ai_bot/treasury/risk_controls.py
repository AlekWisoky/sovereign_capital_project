from __future__ import annotations

from typing import Any, Dict


def drawdown_contraction(
    *, drawdown_pct: float, thresholds: Dict[str, float] | None = None
) -> Dict[str, Any]:
    t = dict(thresholds or {})
    mild = float(t.get("mild", 5.0) or 5.0)
    medium = float(t.get("medium", 10.0) or 10.0)
    severe = float(t.get("severe", 18.0) or 18.0)
    dd = max(0.0, float(drawdown_pct or 0.0))
    if dd >= severe:
        return {
            "contraction_factor": 0.45,
            "reason_code": "severe_drawdown_contraction",
            "experimental_cap_factor": 0.10,
        }
    if dd >= medium:
        return {
            "contraction_factor": 0.65,
            "reason_code": "medium_drawdown_contraction",
            "experimental_cap_factor": 0.35,
        }
    if dd >= mild:
        return {
            "contraction_factor": 0.82,
            "reason_code": "mild_drawdown_contraction",
            "experimental_cap_factor": 0.60,
        }
    return {"contraction_factor": 1.0, "reason_code": "normal", "experimental_cap_factor": 1.0}
