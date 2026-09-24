from __future__ import annotations

"""AI inference latency economics.

AI latency is treated as an execution-time opportunity-decay cost, not as a
generic performance metric. The model is intentionally bounded and uses the
same opportunity half-life already used by execution capture.
"""

from typing import Any, Dict


def ai_latency_survival_factor(
    *, ai_latency_ms: float, latency_half_life_ms: float, learned_factor: float = 1.0
) -> float:
    latency = max(0.0, float(ai_latency_ms))
    half_life = max(1.0, float(latency_half_life_ms))
    # Exponential half-life: 0ms => 1.0, one half-life => 0.5.
    base = 2.0 ** (-latency / half_life)
    return max(0.05, min(1.0, base * max(0.25, min(1.25, float(learned_factor)))))


def ai_latency_cost_usd(
    *, expected_profit_usd: float, ai_latency_ms: float, latency_half_life_ms: float,
    sensitivity: float = 1.0, learned_factor: float = 1.0
) -> float:
    gross = max(0.0, float(expected_profit_usd))
    survival = ai_latency_survival_factor(
        ai_latency_ms=ai_latency_ms,
        latency_half_life_ms=latency_half_life_ms,
        learned_factor=learned_factor,
    )
    return gross * max(0.0, min(1.0, float(sensitivity))) * (1.0 - survival)


def ai_latency_learning_projection(feedback: Dict[str, Any] | None) -> Dict[str, float]:
    """Return an observational, bounded relationship from route telemetry.

    This is deliberately not presented as causal attribution. It estimates how
    much realized/expected edge has historically survived on routes carrying
    measured AI latency.
    """
    row = dict(feedback or {})
    expected = max(0.0, float(row.get("avg_expected_pnl_usd") or 0.0))
    realized = max(0.0, float(row.get("avg_realized_pnl_usd") or 0.0))
    avg_latency = max(0.0, float(row.get("avg_ai_latency_ms") or 0.0))
    ratio = realized / expected if expected > 1e-9 else 1.0
    # Bounded correction: never turns sparse/no-AI history into a strong penalty.
    confidence = max(0.0, min(1.0, float(row.get("ai_latency_samples") or 0.0) / 20.0))
    learned_factor = 1.0 - confidence * max(0.0, min(0.50, 1.0 - ratio))
    return {
        "avg_ai_latency_ms": float(avg_latency),
        "ai_latency_realization_ratio": float(max(0.0, min(1.5, ratio))),
        "ai_latency_learning_confidence": float(confidence),
        "ai_latency_learned_factor": float(max(0.50, min(1.0, learned_factor))),
    }
