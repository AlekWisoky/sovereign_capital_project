from __future__ import annotations

from typing import Any, Dict


def default_route_family_priors(route_family: str) -> Dict[str, Any]:
    fam = str(route_family or "unknown")
    copy_risk = 0.40
    best_lane = "PROTECTED"
    safe_size_upper = 1.0
    if "curve" in fam or "balancer" in fam:
        copy_risk = 0.55
        best_lane = "PRIVATE"
        safe_size_upper = 0.85
    if "flashloan_atomic" in fam:
        safe_size_upper = 1.10
    return {
        "latency_decay_half_life_ms": 900,
        "copy_risk_prior": copy_risk,
        "revert_rate_prior": 0.08,
        "safe_size_upper_mult": safe_size_upper,
        "best_lane": best_lane,
        "best_rpc": "protected",
    }
