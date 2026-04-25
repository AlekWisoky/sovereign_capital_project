from __future__ import annotations

from typing import Iterable, Tuple

from .models import OpportunityEnvelope, CaptureScore, SafeSizePoint


def choose_size(envelope: OpportunityEnvelope, score: CaptureScore) -> Tuple[float, float]:
    best_mult = 1.0
    best_value = score.expected_realized_value
    points = list(envelope.safe_size_curve or [])
    if not points:
        return best_mult, best_value
    for pt in points:
        fragility_penalty = max(
            0.0, (pt.size_mult - 1.0) * envelope.liquidity_fragility * envelope.expected_profit_usd
        )
        confidence_penalty = max(
            0.0,
            (1.0 - score.success_probability)
            * max(0.0, pt.size_mult - 0.75)
            * envelope.expected_profit_usd,
        )
        candidate_value = (
            (
                pt.expected_profit_usd
                * score.success_probability
                * score.freshness_probability
                * (1.0 - score.interference_probability)
                * score.venue_quality
            )
            - envelope.gas_estimate_usd
            - pt.slippage_cost_usd
            - pt.interference_penalty_usd
            - pt.latency_decay_cost_usd
            - score.failure_cost_estimate
            - fragility_penalty
            - confidence_penalty
        )
        if candidate_value > best_value:
            best_mult = float(pt.size_mult)
            best_value = float(candidate_value)
    return float(best_mult), float(best_value)
