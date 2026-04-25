from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass(frozen=True)
class MarketRegime:
    regime: str
    confidence: float
    features: Dict[str, float]
    enabled_strategies: List[str]
    risk_posture: str = "moderate"
    preferred_lane: str = "PROTECTED"
    family_biases: Dict[str, float] | None = None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["family_biases"] = dict(self.family_biases or {})
        return out


FAMILY_BIASES: Dict[str, Dict[str, float]] = {
    "gas_spike": {
        "flashloan_atomic": 0.86,
        "cross_cex_dex": 0.82,
        "funding_arb": 1.04,
        "cross_chain_arb": 0.72,
        "mev_search": 0.98,
    },
    "low_liquidity": {
        "flashloan_atomic": 0.84,
        "cross_cex_dex": 0.78,
        "funding_arb": 1.02,
        "cross_chain_arb": 0.76,
        "mev_search": 0.94,
    },
    "high_volatility": {
        "flashloan_atomic": 1.05,
        "cross_cex_dex": 1.08,
        "funding_arb": 0.92,
        "cross_chain_arb": 0.88,
        "mev_search": 1.12,
    },
    "low_volatility": {
        "flashloan_atomic": 0.96,
        "cross_cex_dex": 0.95,
        "funding_arb": 1.08,
        "cross_chain_arb": 0.98,
        "mev_search": 0.90,
    },
    "bull": {
        "flashloan_atomic": 1.02,
        "cross_cex_dex": 1.00,
        "funding_arb": 1.05,
        "cross_chain_arb": 0.95,
        "mev_search": 1.00,
    },
    "bear": {
        "flashloan_atomic": 1.00,
        "cross_cex_dex": 1.06,
        "funding_arb": 0.98,
        "cross_chain_arb": 0.88,
        "mev_search": 1.08,
    },
    "balanced": {
        "flashloan_atomic": 1.0,
        "cross_cex_dex": 1.0,
        "funding_arb": 1.0,
        "cross_chain_arb": 0.92,
        "mev_search": 1.0,
    },
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _family_from_route_family(route_family: str) -> str:
    fam = str(route_family or "")
    if "cross_cex_dex" in fam:
        return "cross_cex_dex"
    if "funding_arb" in fam or "funding" in fam:
        return "funding_arb"
    if "cross_chain" in fam:
        return "cross_chain_arb"
    if "mev" in fam:
        return "mev_search"
    return "flashloan_atomic"


def classify_market(
    *, volatility: Any, liquidity: Any, volume: Any, gas: Any, spreads: Any, trend: Any = 0.0
) -> MarketRegime:
    vol = max(0.0, min(1.0, _safe_float(volatility)))
    liq = max(0.0, min(1.0, _safe_float(liquidity)))
    volu = max(0.0, min(1.0, _safe_float(volume)))
    gas_v = max(0.0, min(1.0, _safe_float(gas)))
    spr = max(0.0, min(1.0, _safe_float(spreads)))
    tr = max(-1.0, min(1.0, _safe_float(trend)))

    if gas_v >= 0.72:
        return MarketRegime(
            "gas_spike",
            0.82,
            {
                "volatility": vol,
                "liquidity": liq,
                "volume": volu,
                "gas": gas_v,
                "spreads": spr,
                "trend": tr,
            },
            ["flashloan_atomic_private", "protected_atomic"],
            "defensive",
            "PRIVATE",
            FAMILY_BIASES["gas_spike"],
        )
    if liq <= 0.30:
        return MarketRegime(
            "low_liquidity",
            0.78,
            {
                "volatility": vol,
                "liquidity": liq,
                "volume": volu,
                "gas": gas_v,
                "spreads": spr,
                "trend": tr,
            },
            ["small_size_atomic", "protected_atomic"],
            "defensive",
            "PROTECTED",
            FAMILY_BIASES["low_liquidity"],
        )
    if vol >= 0.68:
        return MarketRegime(
            "high_volatility",
            0.84,
            {
                "volatility": vol,
                "liquidity": liq,
                "volume": volu,
                "gas": gas_v,
                "spreads": spr,
                "trend": tr,
            },
            ["fast_atomic", "private_atomic", "latency_sensitive"],
            "opportunistic",
            "PRIVATE",
            FAMILY_BIASES["high_volatility"],
        )
    if vol <= 0.28 and liq >= 0.55:
        return MarketRegime(
            "low_volatility",
            0.72,
            {
                "volatility": vol,
                "liquidity": liq,
                "volume": volu,
                "gas": gas_v,
                "spreads": spr,
                "trend": tr,
            },
            ["durable_atomic", "public_atomic"],
            "moderate",
            "PUBLIC",
            FAMILY_BIASES["low_volatility"],
        )
    if tr >= 0.25 and volu >= 0.45:
        return MarketRegime(
            "bull",
            0.68,
            {
                "volatility": vol,
                "liquidity": liq,
                "volume": volu,
                "gas": gas_v,
                "spreads": spr,
                "trend": tr,
            },
            ["flow_following_atomic", "durable_atomic"],
            "moderate",
            "PROTECTED",
            FAMILY_BIASES["bull"],
        )
    if tr <= -0.25 and volu >= 0.45:
        return MarketRegime(
            "bear",
            0.68,
            {
                "volatility": vol,
                "liquidity": liq,
                "volume": volu,
                "gas": gas_v,
                "spreads": spr,
                "trend": tr,
            },
            ["defensive_atomic", "private_atomic"],
            "defensive",
            "PRIVATE",
            FAMILY_BIASES["bear"],
        )
    return MarketRegime(
        "balanced",
        0.60,
        {
            "volatility": vol,
            "liquidity": liq,
            "volume": volu,
            "gas": gas_v,
            "spreads": spr,
            "trend": tr,
        },
        ["flashloan_atomic"],
        "moderate",
        "PROTECTED",
        FAMILY_BIASES["balanced"],
    )


def regime_adjustments(*, route_family: str, regime: str) -> Dict[str, float | str]:
    fam = _family_from_route_family(route_family)
    reg = str(regime or "balanced")
    bias = float((FAMILY_BIASES.get(reg) or FAMILY_BIASES["balanced"]).get(fam, 1.0))
    preferred_lane = "PROTECTED"
    if reg in {"high_volatility", "gas_spike", "bear"}:
        preferred_lane = "PRIVATE"
    elif reg == "low_volatility" and fam in {"flashloan_atomic"}:
        preferred_lane = "PUBLIC"
    elif fam == "funding_arb":
        preferred_lane = "PROTECTED"
    if fam == "cross_chain_arb":
        preferred_lane = "PRIVATE" if reg in {"bear", "high_volatility"} else "PROTECTED"
    return {
        "family": fam,
        "value_multiplier": max(0.70, min(1.20, bias)),
        "confidence_multiplier": max(0.80, min(1.15, 0.9 + (bias - 1.0) * 0.8)),
        "preferred_lane": preferred_lane,
    }
