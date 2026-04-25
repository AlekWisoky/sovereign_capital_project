from __future__ import annotations

import math


def net_profit_usd(
    *,
    spread: float,
    volume: float,
    fees_usd: float = 0.0,
    slippage_usd: float = 0.0,
    transfer_usd: float = 0.0,
    gas_usd: float = 0.0,
    vol_risk_usd: float = 0.0,
) -> float:
    """Compute net profit (USD) from a spread opp.

    profit = spread*volume - fees - slippage - transfer - gas - vol_risk
    """

    return float(spread) * float(volume) - float(fees_usd) - float(slippage_usd) - float(transfer_usd) - float(gas_usd) - float(vol_risk_usd)


def alpha_score(
    *,
    profit_usd: float,
    capital_usd: float,
    funding_adjust: float = 0.0,
    liquidity_penalty: float = 0.0,
    volatility_penalty: float = 0.0,
    latency_penalty: float = 0.0,
    transfer_penalty: float = 0.0,
) -> float:
    """Compute alpha score used for execution gating.

    alpha = (profit/capital) + funding_adjust - liquidity_penalty - volatility_penalty - latency_penalty - transfer_penalty

    Deterministic and bounded.
    """

    cap = max(1e-9, float(capital_usd))
    base = float(profit_usd) / cap
    a = base + float(funding_adjust) - float(liquidity_penalty) - float(volatility_penalty) - float(latency_penalty) - float(transfer_penalty)
    # soft clamp to avoid absurd values
    return float(max(-5.0, min(5.0, a)))


def logistic(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-float(x)))
    except (OverflowError, TypeError, ValueError):
        return 0.5
