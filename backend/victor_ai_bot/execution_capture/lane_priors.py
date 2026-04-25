from __future__ import annotations

from typing import Dict


def default_lane_priors(*, lane: str, regime: str = "") -> Dict[str, float]:
    lane_u = str(lane or "PUBLIC").upper()
    pri = {
        "success_bias": 0.0,
        "realization_bias": 0.0,
        "copy_risk_bias": 0.0,
    }
    if lane_u == "PRIVATE":
        pri.update({"success_bias": 0.04, "realization_bias": 0.06, "copy_risk_bias": -0.10})
    elif lane_u == "PROTECTED":
        pri.update({"success_bias": 0.02, "realization_bias": 0.03, "copy_risk_bias": -0.05})
    else:
        pri.update({"success_bias": -0.01, "realization_bias": -0.02, "copy_risk_bias": 0.04})
    if str(regime or "") in {"high_volatility", "gas_spike"} and lane_u == "PUBLIC":
        pri["success_bias"] -= 0.03
        pri["realization_bias"] -= 0.04
    return pri
