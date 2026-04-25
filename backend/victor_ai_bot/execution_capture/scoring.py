from __future__ import annotations

from typing import Dict

from .models import OpportunityEnvelope, CaptureScore


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_capture_score(
    envelope: OpportunityEnvelope, telemetry: Dict[str, float]
) -> CaptureScore:
    route_success = float(telemetry.get("route_success_rate", 0.65) or 0.65)
    lane_success = float(telemetry.get("lane_success_rate", 0.65) or 0.65)
    venue_success = float(telemetry.get("venue_success_rate", 0.65) or 0.65)
    venue_quality_feedback = float(telemetry.get("venue_quality", 0.8) or 0.8)
    stale_rate = max(
        float(telemetry.get("route_stale_rate", 0.05) or 0.05),
        float(telemetry.get("lane_stale_rate", 0.03) or 0.03),
    )
    timeout_rate = float(telemetry.get("lane_timeout_rate", 0.02) or 0.02)
    revert_rate = float(telemetry.get("lane_revert_rate", 0.04) or 0.04)
    quote_drift_bps = float(telemetry.get("route_quote_drift_bps", 0.0) or 0.0)
    endpoint_quality = float(telemetry.get("endpoint_quality", 0.75) or 0.75)
    lane_avg_latency_ms = float(telemetry.get("lane_avg_latency_ms", 700.0) or 700.0)
    latency_pressure = float(telemetry.get("latency_pressure", 0.0) or 0.0)

    success_probability = _clip(
        (0.40 * envelope.simulation_confidence)
        + (0.18 * envelope.venue_reliability_score)
        + (0.16 * route_success)
        + (0.12 * venue_success)
        + (0.14 * endpoint_quality),
        0.0,
        0.995,
    )
    decay_factor = float(envelope.latency_half_life_ms) / float(
        max(1, envelope.latency_half_life_ms + 200)
    )
    freshness_probability = _clip(
        (0.55 * envelope.freshness_score)
        + (0.15 * (1.0 - stale_rate))
        + (0.10 * decay_factor)
        + (
            0.10
            * max(0.0, 1.0 - lane_avg_latency_ms / max(350.0, float(envelope.latency_half_life_ms)))
        ),
        0.0,
        0.995,
    )
    interference_probability = _clip(
        (0.62 * envelope.mempool_copy_risk)
        + (0.15 * stale_rate)
        + (0.13 * timeout_rate)
        + (0.10 * latency_pressure),
        0.0,
        0.995,
    )
    non_interference_probability = 1.0 - interference_probability
    venue_quality = _clip(
        (0.60 * envelope.venue_reliability_score) + (0.40 * venue_quality_feedback), 0.20, 1.20
    )

    slippage_cost_estimate = (
        envelope.expected_profit_usd
        * envelope.slippage_sensitivity
        * max(0.12, envelope.liquidity_fragility)
        * 0.18
    )
    slippage_cost_estimate += max(0.0, quote_drift_bps) * 0.005
    latency_decay_cost = (
        envelope.expected_profit_usd
        * (1.0 - freshness_probability)
        * max(0.10, envelope.liquidity_fragility)
        * (0.10 + latency_pressure * 0.08)
    )
    failure_probability = _clip(
        (1.0 - success_probability) + (revert_rate * 0.30) + (timeout_rate * 0.20), 0.0, 0.95
    )
    failure_cost_estimate = envelope.failure_cost_estimate * failure_probability

    expected_realized_pnl = (
        (
            envelope.expected_profit_usd
            * success_probability
            * freshness_probability
            * non_interference_probability
            * venue_quality
        )
        - envelope.gas_estimate_usd
        - slippage_cost_estimate
        - latency_decay_cost
        - failure_cost_estimate
    )
    capture_score = expected_realized_pnl
    return CaptureScore(
        success_probability=float(success_probability),
        freshness_probability=float(freshness_probability),
        interference_probability=float(interference_probability),
        venue_quality=float(venue_quality),
        expected_realized_pnl=float(expected_realized_pnl),
        capture_score=float(capture_score),
        expected_realized_value=float(expected_realized_pnl),
        slippage_cost_estimate=float(slippage_cost_estimate),
        latency_decay_cost=float(latency_decay_cost),
        failure_cost_estimate=float(failure_cost_estimate),
        telemetry_adjustments={
            "route_success_rate": float(route_success),
            "lane_success_rate": float(lane_success),
            "venue_success_rate": float(venue_success),
            "stale_rate": float(stale_rate),
            "timeout_rate": float(timeout_rate),
            "revert_rate": float(revert_rate),
            "endpoint_quality": float(endpoint_quality),
            "lane_avg_latency_ms": float(lane_avg_latency_ms),
            "latency_pressure": float(latency_pressure),
        },
    )
