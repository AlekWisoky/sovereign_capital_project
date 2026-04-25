from __future__ import annotations

from typing import Any, Dict

from .models import OpportunityEnvelope


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def simulate_execution_realism(
    *,
    envelope: OpportunityEnvelope,
    telemetry: Dict[str, Any],
    regime: str = "balanced",
    lane_hint: str = "",
) -> Dict[str, float]:
    """Production-friendly execution realism overlay.

    It approximates the main reasons projected edge fails to realize:
    gas-auction pressure, depth saturation, public mempool competition,
    quote drift, and venue instability. All outputs are interpretable scalars.
    """
    quote_drift_bps = max(0.0, float(telemetry.get("route_quote_drift_bps", 0.0) or 0.0))
    timeout_rate = _clip(float(telemetry.get("lane_timeout_rate", 0.02) or 0.02), 0.0, 1.0)
    revert_rate = _clip(float(telemetry.get("lane_revert_rate", 0.04) or 0.04), 0.0, 1.0)
    venue_failure = _clip(1.0 - float(telemetry.get("venue_success_rate", 0.7) or 0.7), 0.0, 1.0)

    safe_curve = list(envelope.safe_size_curve or [])
    base_curve = safe_curve[0] if safe_curve else None
    top_curve = safe_curve[-1] if safe_curve else None
    depth_ratio = 0.0
    if (
        base_curve is not None
        and top_curve is not None
        and float(base_curve.expected_profit_usd) > 0
    ):
        top_drag = float(
            top_curve.slippage_cost_usd
            + top_curve.interference_penalty_usd
            + top_curve.latency_decay_cost_usd
        )
        base_drag = float(
            base_curve.slippage_cost_usd
            + base_curve.interference_penalty_usd
            + base_curve.latency_decay_cost_usd
        )
        depth_ratio = _clip(
            (top_drag - base_drag) / max(1e-9, float(top_curve.expected_profit_usd)), 0.0, 1.0
        )

    gas_auction_pressure = _clip(
        (quote_drift_bps / 40.0) * 0.35
        + timeout_rate * 0.45
        + (0.15 if regime == "gas_spike" else 0.0),
        0.0,
        0.95,
    )
    mev_competition_penalty = _clip(
        envelope.mempool_copy_risk * 0.60
        + timeout_rate * 0.10
        + (0.18 if regime == "high_volatility" else 0.0),
        0.0,
        0.95,
    )

    lane_key = str(lane_hint or "").strip().lower()
    if lane_key == "private":
        mev_competition_penalty *= 0.50
        gas_auction_pressure *= 0.90
    elif lane_key in {"protected", "protected_rpc"}:
        mev_competition_penalty *= 0.72
        gas_auction_pressure *= 0.95
    depth_penalty = _clip(depth_ratio * 0.70 + envelope.liquidity_fragility * 0.25, 0.0, 0.95)
    venue_instability_penalty = _clip(venue_failure * 0.50 + revert_rate * 0.35, 0.0, 0.95)

    success_multiplier = _clip(
        1.0
        - (
            gas_auction_pressure * 0.10
            + mev_competition_penalty * 0.18
            + venue_instability_penalty * 0.16
        ),
        0.35,
        1.05,
    )
    freshness_multiplier = _clip(
        1.0 - (gas_auction_pressure * 0.18 + quote_drift_bps / 300.0), 0.25, 1.00
    )
    non_interference_multiplier = _clip(1.0 - (mev_competition_penalty * 0.28), 0.20, 1.00)

    added_gas_cost = float(envelope.gas_estimate_usd) * gas_auction_pressure * 0.35
    added_slippage_cost = (
        float(envelope.expected_profit_usd)
        * depth_penalty
        * max(0.08, envelope.slippage_sensitivity * 0.25)
    )
    added_failure_cost = float(envelope.failure_cost_estimate) * venue_instability_penalty * 0.30
    if lane_key == "private":
        added_slippage_cost *= 0.45
        added_failure_cost *= 0.65
    elif lane_key in {"protected", "protected_rpc"}:
        added_slippage_cost *= 0.72
        added_failure_cost *= 0.82
    realism_confidence = _clip(
        1.0 - (depth_penalty * 0.25 + venue_instability_penalty * 0.20), 0.20, 1.00
    )

    return {
        "gas_auction_pressure": gas_auction_pressure,
        "mev_competition_penalty": mev_competition_penalty,
        "depth_penalty": depth_penalty,
        "venue_instability_penalty": venue_instability_penalty,
        "success_multiplier": success_multiplier,
        "freshness_multiplier": freshness_multiplier,
        "non_interference_multiplier": non_interference_multiplier,
        "added_gas_cost": added_gas_cost,
        "added_slippage_cost": added_slippage_cost,
        "added_failure_cost": added_failure_cost,
        "realism_confidence": realism_confidence,
    }
