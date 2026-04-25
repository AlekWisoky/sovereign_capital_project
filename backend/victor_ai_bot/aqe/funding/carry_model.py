from __future__ import annotations

from typing import Dict


def carry_horizon_score(*, rate_diff: float, hours_to_funding: float, basis_bps: float, venue_fee_bps: float) -> Dict[str, float]:
    carry = max(0.0, float(rate_diff)) * max(1.0, 8.0 / max(1.0, float(hours_to_funding)))
    basis_penalty = abs(float(basis_bps)) / 10_000.0
    fee_penalty = float(venue_fee_bps) / 10_000.0
    realized_edge = carry - basis_penalty - fee_penalty
    return {
        'carry_per_period': round(carry, 8),
        'basis_penalty': round(basis_penalty, 8),
        'fee_penalty': round(fee_penalty, 8),
        'realized_edge_ratio': round(realized_edge, 8),
    }
