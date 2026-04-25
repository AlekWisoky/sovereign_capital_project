from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from victor_ai_bot.regime_engine import classify_market


@dataclass
class Regime:
    name: str
    confidence: float
    features: Dict[str, float]


def detect_regime(telemetry: Dict[str, Any]) -> Regime:
    vol = float(telemetry.get('volatility_proxy') or 0.0)
    basefee = float(telemetry.get('basefee_gwei') or 0.0)
    sr = float(telemetry.get('success_rate') or 0.0)
    opp_rate = float(telemetry.get('opportunity_rate') or 0.0)
    liq = max(0.05, min(1.0, 1.0 - max(0.0, min(1.0, vol * 0.55 + float(telemetry.get('route_fail_rate') or 0.0) * 0.45))))
    gas_norm = min(1.0, basefee / 100.0)
    trend = (opp_rate - 1.0) * 0.25 + (sr - 0.5) * 0.5
    market = classify_market(volatility=vol, liquidity=liq, volume=min(1.0, opp_rate / 3.0), gas=gas_norm, spreads=min(1.0, vol + (1.0 - sr)), trend=trend)
    return Regime(name=market.regime, confidence=float(market.confidence), features=dict(market.features or {}))
