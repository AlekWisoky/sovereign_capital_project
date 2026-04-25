from __future__ import annotations

from typing import Any, Dict


def competition_penalty(
    *, route_family: str, mempool_copy_risk: float, venue_quality: float, lane: str
) -> Dict[str, Any]:
    base = 0.0
    if str(route_family) in {"flashloan_atomic", "flash_arb", "liquidation_capture"}:
        base += 0.22
    base += max(0.0, float(mempool_copy_risk)) * 0.45
    base += max(0.0, 0.6 - float(venue_quality)) * 0.20
    if str(lane).upper() in {"PRIVATE", "PROTECTED"}:
        base *= 0.55
    return {
        "competitionPenalty": round(min(0.85, base), 6),
        "reasonCodes": ["competition_model_applied"],
    }
