from __future__ import annotations

from typing import Dict

from .models import OpportunityEnvelope, CaptureScore
from ..fund_os.profit_doctrine import executable_edge_objective


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

    # Canonical pre-settlement ranking objective. Deterministic costs are
    # removed before the quality factors are applied; failure/reliability is
    # represented by the explicit execution_reliability factor.
    extra_costs = sum(
        max(0.0, float(telemetry.get(key, 0.0) or 0.0))
        for key in (
            "flashloan_fee_usd",
            "bridge_fee_usd",
            "private_execution_cost_usd",
        )
    )
    executable_net_profit = max(
        0.0,
        envelope.expected_profit_usd
        - envelope.gas_estimate_usd
        - slippage_cost_estimate
        - extra_costs,
    )
    liquidity_quality = _clip(
        float(telemetry.get("liquidity_quality", 1.0 - envelope.liquidity_fragility) or 0.0),
        0.0,
        1.0,
    )
    execution_reliability = _clip(
        route_success
        * venue_success
        * lane_success
        * (1.0 - revert_rate)
        * (1.0 - timeout_rate),
        0.0,
        1.0,
    )
    objective = executable_edge_objective(
        executable_net_profit=executable_net_profit,
        probability_of_success=success_probability,
        route_quality=venue_quality,
        liquidity_quality=liquidity_quality,
        capital_efficiency=float(telemetry.get("capital_efficiency_factor", 1.0) or 1.0),
        latency_survivability=freshness_probability,
        execution_reliability=execution_reliability,
    )
    realized_edge = float(objective["realizedEdge"])

    capture_score = realized_edge
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
            "liquidity_quality": float(liquidity_quality),
            "execution_reliability": float(execution_reliability),
            "capital_efficiency_factor": float(objective["capitalEfficiency"]),
            "executable_net_profit": float(objective["executableNetProfit"]),
            "extra_execution_costs": float(extra_costs),
        },
        realized_edge=realized_edge,
        objective_components={
            "executableNetProfit": float(objective["executableNetProfit"]),
            "probabilityOfSuccess": float(objective["probabilityOfSuccess"]),
            "routeQuality": float(objective["routeQuality"]),
            "liquidityQuality": float(objective["liquidityQuality"]),
            "capitalEfficiency": float(objective["capitalEfficiency"]),
            "latencySurvivability": float(objective["latencySurvivability"]),
            "executionReliability": float(objective["executionReliability"]),
        },
    )
