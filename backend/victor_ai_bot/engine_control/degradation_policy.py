from __future__ import annotations


def degradation_mode_for(
    *,
    confidence: float,
    telemetry_points: int,
    calibration_points: int,
    risk_flags: list[str] | None = None,
) -> str:
    flags = set(risk_flags or [])
    if "unsafe" in flags or "policy_disallowed" in flags:
        return "disabled"
    if confidence < 0.45 or telemetry_points < 5:
        return "observe_only"
    if confidence < 0.60 or calibration_points < 10 or {"bridge_risk", "settlement_risk"} & flags:
        return "paper"
    if confidence < 0.72 or {"inventory_thin", "latency_high"} & flags:
        return "capped_live"
    return "live"
