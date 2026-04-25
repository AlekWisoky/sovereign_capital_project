from __future__ import annotations

from typing import Dict


def bridge_risk_model(*, finality_seconds: float, bridge_fee_bps: float, timeout_probability: float) -> Dict[str, float]:
    finality_penalty = min(0.20, max(0.0, float(finality_seconds) / 7200.0))
    fee_penalty = float(bridge_fee_bps) / 10_000.0
    timeout_penalty = max(0.0, min(0.40, float(timeout_probability)))
    total = finality_penalty + fee_penalty + timeout_penalty
    return {
        'penalty_ratio': round(total, 8),
        'finality_penalty': round(finality_penalty, 8),
        'fee_penalty': round(fee_penalty, 8),
        'timeout_penalty': round(timeout_penalty, 8),
    }
