from __future__ import annotations

from typing import Any, Dict


def retirement_reason(
    *, robustness: float, realized_edge_usd: float, overlap_penalty: float, regime_fit: float
) -> str:
    if robustness < 0.35:
        return "robustness_gate_failure"
    if realized_edge_usd < 0.0:
        return "alpha_decay"
    if overlap_penalty > 0.65:
        return "excessive_overlap"
    if regime_fit < 0.35:
        return "regime_mismatch"
    return "none"
