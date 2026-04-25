from __future__ import annotations

from typing import Any, Dict


def thin_edge_admission(
    *,
    projected_realized_edge_usd: float,
    competition_penalty: float,
    confidence: float,
    venue_quality: float,
) -> Dict[str, Any]:
    adjusted = float(projected_realized_edge_usd) * max(0.05, 1.0 - float(competition_penalty))
    allowed = adjusted > 0.0 and float(confidence) >= 0.70 and float(venue_quality) >= 0.45
    return {
        "allowed": bool(allowed),
        "adjustedEdgeUsd": round(adjusted, 8),
        "reason": "ok" if allowed else "thin_edge_suppressed",
    }
