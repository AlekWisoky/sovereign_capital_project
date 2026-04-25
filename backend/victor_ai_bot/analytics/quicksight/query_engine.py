from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError)

from .rbac import (
    PERM_ASK_ANALYTICS,
    PERM_GENERATE_SUMMARY,
    PERM_VIEW_DASHBOARDS,
    has_permission,
)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except _SAFE_FLOAT_EXCEPTIONS:
        try:
            return float(str(x))
        except _SAFE_FLOAT_EXCEPTIONS:
            return float(default)


def _simple_forecast(series: List[Tuple[int, float]], horizon_points: int = 10) -> List[Tuple[int, float]]:
    """Deterministic forecast: linear extrapolation on last 5 points."""
    if not series:
        return []
    pts = series[-5:] if len(series) >= 5 else series
    if len(pts) < 2:
        return []
    t0, y0 = pts[0]
    t1, y1 = pts[-1]
    dt = max(1, t1 - t0)
    slope = (y1 - y0) / float(dt)

    out: List[Tuple[int, float]] = []
    last_t, last_y = series[-1]
    step = max(1, dt // max(1, (len(pts) - 1)))
    for i in range(1, horizon_points + 1):
        t = last_t + i * step
        y = last_y + slope * float(i * step)
        out.append((int(t), float(y)))
    return out


class GenerativeQueryEngine:
    """Deterministic natural-language analytics interface.

    This does NOT call external APIs or models. It's a keyword-router over
    the BI datasets and dashboards already stored in memory.
    """

    def ask(
        self,
        *,
        question: str,
        role: str,
        datasets: Dict[str, List[Dict[str, Any]]],
        dashboards: Dict[str, Any],
        income: Dict[str, Any],
    ) -> Dict[str, Any]:
        q = str(question or "").strip()
        if not q:
            return {"ok": False, "error": "empty_question"}

        if not has_permission(role, PERM_ASK_ANALYTICS):
            return {"ok": False, "error": "forbidden"}

        ql = q.lower()

        if "executive" in ql or "summary" in ql:
            if not has_permission(role, PERM_GENERATE_SUMMARY):
                return {"ok": False, "error": "forbidden"}
            dash = dashboards.get("EXECUTIVE_OVERVIEW") or {}
            return {
                "ok": True,
                "type": "GENERATE_EXECUTIVE_SUMMARY",
                "json_summary": {"executive_overview": (dash.get("kpis") or {}), "income_streams": income},
                "visualization": {"dashboard": "EXECUTIVE_OVERVIEW"},
                "narrative": self._narrative_exec(dash=dash, income=income),
                "confidence": 0.75,
            }

        if "income" in ql or "stream" in ql:
            return {
                "ok": True,
                "type": "ASK_ANALYTICS",
                "json_summary": {"income": income},
                "visualization": {"dashboard": "EXECUTIVE_OVERVIEW"},
                "narrative": self._narrative_income(income=income),
                "confidence": 0.70,
            }

        if "trend" in ql or "over time" in ql or "timeseries" in ql:
            metric = self._pick_metric(ql)
            ds = datasets.get("TRADING_METRICS") or []
            series: List[Tuple[int, float]] = []
            for row in ds[-200:]:
                if not isinstance(row, dict):
                    continue
                if str(row.get("strategy_id")) != "ALL":
                    continue
                series.append((int(row.get("timestamp") or 0), _safe_float(row.get(metric), 0.0)))

            return {
                "ok": True,
                "type": "SHOW_TREND",
                "json_summary": {"metric": metric, "points": series[-60:]},
                "visualization": {"dataset": "TRADING_METRICS", "metric": metric},
                "narrative": f"Trend for {metric} (showing last {len(series[-60:])} points).",
                "confidence": 0.60,
            }

        if "forecast" in ql or "predict" in ql:
            metric = self._pick_metric(ql)
            ds = datasets.get("TRADING_METRICS") or []
            series2: List[Tuple[int, float]] = []
            for row in ds[-200:]:
                if not isinstance(row, dict):
                    continue
                if str(row.get("strategy_id")) != "ALL":
                    continue
                series2.append((int(row.get("timestamp") or 0), _safe_float(row.get(metric), 0.0)))

            fore = _simple_forecast(series2, horizon_points=10)
            return {
                "ok": True,
                "type": "FORECAST_METRIC",
                "json_summary": {"metric": metric, "forecast": fore},
                "visualization": {"dataset": "TRADING_METRICS", "metric": metric},
                "narrative": f"Simple linear forecast for {metric} ({len(fore)} steps).",
                "confidence": 0.45,
            }

        if "anomal" in ql or "breach" in ql or "alert" in ql:
            return {
                "ok": True,
                "type": "EXPLAIN_ANOMALY",
                "json_summary": {"hint": "Inspect threat monitor scores and circuit breaker status."},
                "visualization": {"dashboard": "RISK_CONTROL_PANEL"},
                "narrative": "Use the RISK_CONTROL_PANEL dashboard to inspect threat monitor scores and circuit breaker status.",
                "confidence": 0.40,
            }

        if has_permission(role, PERM_VIEW_DASHBOARDS):
            return {
                "ok": True,
                "type": "ASK_ANALYTICS",
                "json_summary": {"dashboards": list(dashboards.keys())},
                "visualization": {"dashboard": "EXECUTIVE_OVERVIEW"},
                "narrative": "Ask about income streams, PnL, win-rate, drawdown, regime context, risk panel, agent performance, or forecasts.",
                "confidence": 0.40,
            }

        return {"ok": False, "error": "unsupported"}

    def _pick_metric(self, ql: str) -> str:
        if "win" in ql:
            return "win_rate"
        if "sharpe" in ql:
            return "sharpe_ratio"
        if "drawdown" in ql:
            return "drawdown"
        if "pnl" in ql or "profit" in ql:
            return "realized_pnl_wei"
        return "win_rate"

    def _narrative_exec(self, *, dash: Dict[str, Any], income: Dict[str, Any]) -> str:
        k = (dash or {}).get("kpis") or {}
        net = k.get("net_pnl_wei")
        wr = k.get("win_rate")
        trades = k.get("trades")
        by_stream = (income or {}).get("by_income_stream") or {}
        top = sorted(by_stream.items(), key=lambda kv: int((kv[1] or {}).get("pnl_wei") or 0), reverse=True)[:3]
        top_txt = ", ".join([f"{s}({(d or {}).get('pnl_wei')})" for s, d in top]) if top else "n/a"
        return f"Net PnL(wei): {net}; win_rate: {wr}; trades: {trades}. Top income streams: {top_txt}."

    def _narrative_income(self, *, income: Dict[str, Any]) -> str:
        by_stream = (income or {}).get("by_income_stream") or {}
        if not by_stream:
            return "No income stream data yet. Execute some trades to populate PnL analytics."
        top = sorted(by_stream.items(), key=lambda kv: int((kv[1] or {}).get("pnl_wei") or 0), reverse=True)[:5]
        parts = []
        for s, d in top:
            parts.append(
                f"{s}: pnl_wei={d.get('pnl_wei')} win_rate={round(float(d.get('win_rate') or 0.0), 3)} n={d.get('n')}"
            )
        return "Income stream breakdown (top): " + "; ".join(parts)
