from __future__ import annotations

from typing import Any, Dict, List, Tuple


_SAFE_FUNDING_SHARE_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def simulate_scenario(
    *,
    base_metrics: Dict[str, Any],
    income: Dict[str, Any],
    hypothetical_volatility_change: float = 0.0,
    capital_shift: float = 0.0,
    funding_rate_spike: float = 0.0,
    aggressiveness_adjustment: float = 0.0,
) -> Dict[str, Any]:
    """Advisory what-if simulator.

    Inputs:
      - hypothetical_volatility_change: delta (e.g. +0.2 means higher vol)
      - capital_shift: delta fraction of capital deployed (e.g. +0.1)
      - funding_rate_spike: delta (0..1 proxy)
      - aggressiveness_adjustment: delta (e.g. +0.2)

    Output:
      - projected performance series (toy)
      - risk score delta
      - recommendation
    """

    bm = dict(base_metrics or {})
    win_rate = float(bm.get("win_rate") or 0.0)
    sharpe = float(bm.get("sharpe_ratio") or 0.0)
    drawdown = float(bm.get("drawdown") or 0.0)

    # Adjust metrics
    vol = float(hypothetical_volatility_change)
    agg = float(aggressiveness_adjustment)
    cap = float(capital_shift)

    # Higher vol reduces win rate and sharpe, increases drawdown
    win_rate2 = _clip(win_rate * (1.0 - vol * 0.25), 0.0, 1.0)
    sharpe2 = sharpe * (1.0 - vol * 0.35)
    drawdown2 = max(0.0, drawdown * (1.0 + vol * 0.60))

    # Aggressiveness increases pnl potential but increases drawdown further
    sharpe2 = sharpe2 * (1.0 + agg * 0.15)
    drawdown2 = drawdown2 * (1.0 + abs(agg) * 0.40)

    # Capital shift scales PnL linearly in this toy model
    pnl_scale = max(0.0, 1.0 + cap)

    # Funding spike helps funding income stream (if present)
    by_stream = (income or {}).get("by_income_stream") or {}
    funding_share = 0.0
    try:
        total = sum(int((d or {}).get("pnl_wei") or 0) for d in by_stream.values()) or 0
        if total > 0 and "funding" in by_stream:
            funding_share = int((by_stream.get("funding") or {}).get("pnl_wei") or 0) / float(total)
    except _SAFE_FUNDING_SHARE_EXCEPTIONS:
        funding_share = 0.0
    pnl_scale = pnl_scale * (1.0 + float(funding_rate_spike) * 0.20 * float(funding_share))

    # Risk score: combine drawdown and volatility
    risk0 = _clip(drawdown * 0.8 + max(0.0, -sharpe) * 0.1, 0.0, 1.0)
    risk1 = _clip(drawdown2 * 0.8 + max(0.0, -sharpe2) * 0.1 + abs(vol) * 0.1, 0.0, 1.0)
    risk_delta = risk1 - risk0

    # Projected return delta proxy
    ret0 = _clip(sharpe * win_rate, -1.0, 1.0)
    ret1 = _clip(sharpe2 * win_rate2, -1.0, 1.0) * pnl_scale
    ret_delta = ret1 - ret0

    rec = "hold"
    if risk_delta < 0.0 and ret_delta > 0.0:
        rec = "increase_exposure"
    elif risk_delta > 0.05 and ret_delta <= 0.0:
        rec = "decrease_exposure"

    # Create a tiny projected series (10 points)
    series: List[Tuple[int, float]] = []
    for i in range(10):
        series.append((i, float(ret0 + (ret_delta * (i + 1) / 10.0))))

    return {
        "inputs": {
            "hypothetical_volatility_change": float(vol),
            "capital_shift": float(cap),
            "funding_rate_spike": float(funding_rate_spike),
            "aggressiveness_adjustment": float(agg),
        },
        "base": {"win_rate": win_rate, "sharpe_ratio": sharpe, "drawdown": drawdown},
        "projected": {"win_rate": win_rate2, "sharpe_ratio": sharpe2, "drawdown": drawdown2, "pnl_scale": pnl_scale},
        "projected_series": series,
        "risk_score_delta": float(risk_delta),
        "projected_return_delta": float(ret_delta),
        "recommendation": rec,
    }
