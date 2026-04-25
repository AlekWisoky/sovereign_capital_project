from __future__ import annotations

from typing import Any, Dict

from .models import OpportunityEnvelope


def build_edge_features(
    *,
    envelope: OpportunityEnvelope,
    regime: str,
    lane_hint: str,
    telemetry: Dict[str, float],
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ctx = dict(context or {})
    spread = float(envelope.expected_profit_usd)
    gas = float(envelope.gas_estimate_usd)
    projected_realized = max(-9999.0, spread - gas)
    return {
        "route_family": str(envelope.route_family),
        "strategy_family": str(envelope.metadata.get("strategy_family") or envelope.route_family),
        "engine_type": str(envelope.metadata.get("engine_type") or ""),
        "chain_id": int(envelope.chain_id),
        "venues": list(envelope.venues),
        "token_pair": "/".join(list(envelope.token_path[:2])),
        "notional_usd": float(ctx.get("notional_usd") or max(1.0, spread * 1000.0)),
        "spread_usd": spread,
        "projected_realized_profit_usd": projected_realized,
        "gas_estimate_usd": gas,
        "borrow_cost_usd": float(ctx.get("borrow_cost_usd") or 0.0),
        "slippage_prediction": float(
            ctx.get("slippage_prediction") or envelope.slippage_sensitivity
        ),
        "latency_estimate_ms": int(ctx.get("latency_estimate_ms") or envelope.latency_half_life_ms),
        "lane_hint": str(lane_hint or ""),
        "mempool_copy_risk": float(envelope.mempool_copy_risk),
        "liquidity_fragility": float(envelope.liquidity_fragility),
        "freshness_score": float(envelope.freshness_score),
        "venue_reliability_score": float(envelope.venue_reliability_score),
        "simulation_confidence": float(envelope.simulation_confidence),
        "regime": str(regime or "balanced"),
        "telemetry_route_success": float(telemetry.get("route_success_rate", 0.65) or 0.65),
        "telemetry_lane_success": float(telemetry.get("lane_success_rate", 0.65) or 0.65),
        "telemetry_stale_rate": float(telemetry.get("route_stale_rate", 0.05) or 0.05),
        "telemetry_quote_drift_bps": float(telemetry.get("route_quote_drift_bps", 0.0) or 0.0),
    }


def feature_key(features: Dict[str, Any]) -> str:
    venue = str((features.get("venues") or [""])[0])
    return "|".join(
        [
            str(features.get("strategy_family") or ""),
            str(features.get("route_family") or ""),
            venue,
            str(features.get("lane_hint") or ""),
            str(features.get("regime") or ""),
        ]
    )
