from __future__ import annotations

from typing import Any, Dict, Iterable

from .backtest_engine import run_backtest


def evaluate_strategy(samples: Iterable[Dict[str, Any]], *, min_avg_pnl_usd: float = 0.0) -> Dict[str, Any]:
    bt = run_backtest(samples)
    return {'allowed': float(bt.get('avgPnlUsd', 0.0)) >= float(min_avg_pnl_usd), 'backtest': bt}
