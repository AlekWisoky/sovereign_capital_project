from __future__ import annotations

import math
from victor_ai_bot.runtime_services.treasury_governance_truth import treasury_governance_view
from typing import Any, Dict, List, Tuple

_SAFE_INT_EXCEPTIONS = (TypeError, ValueError, OverflowError)
_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError, OverflowError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _runtime_bucket() -> Dict[str, Any]:
    return {"count": 0, "code": "", "degraded": False}


def _init_status(*names: str) -> Dict[str, Any]:
    status: Dict[str, Any] = {name: _runtime_bucket() for name in names}
    status["degraded"] = False
    return status


def _mark_status(status: Dict[str, Any], bucket: str, code: str) -> None:
    entry = status.get(bucket)
    if not isinstance(entry, dict):
        entry = _runtime_bucket()
        status[bucket] = entry
    entry["count"] = int(entry.get("count") or 0) + 1
    entry["code"] = str(code or "")
    entry["degraded"] = True
    status["degraded"] = True


def _safe_int(
    x: Any,
    default: int = 0,
    *,
    status: Dict[str, Any] | None = None,
    bucket: str = "",
    code: str = "",
) -> int:
    try:
        if x is None or isinstance(x, bool):
            return int(default)
        return int(x)
    except _SAFE_INT_EXCEPTIONS:
        try:
            if x is None or isinstance(x, bool):
                return int(default)
            return int(str(x))
        except _SAFE_INT_EXCEPTIONS:
            if status is not None and bucket:
                _mark_status(status, bucket, code or "int_invalid")
            return int(default)


def _safe_float(
    x: Any,
    default: float = 0.0,
    *,
    status: Dict[str, Any] | None = None,
    bucket: str = "",
    code: str = "",
) -> float:
    try:
        if x is None or isinstance(x, bool):
            return float(default)
        return float(x)
    except _SAFE_FLOAT_EXCEPTIONS:
        try:
            if x is None or isinstance(x, bool):
                return float(default)
            return float(str(x))
        except _SAFE_FLOAT_EXCEPTIONS:
            if status is not None and bucket:
                _mark_status(status, bucket, code or "float_invalid")
            return float(default)


def max_drawdown(returns: List[float]) -> float:
    """Max drawdown on cumulative sum series of returns."""
    if not returns:
        return 0.0
    peak = 0.0
    cur = 0.0
    mdd = 0.0
    for r in returns:
        cur += _safe_float(r, 0.0)
        peak = max(peak, cur)
        dd = peak - cur
        mdd = max(mdd, dd)
    return float(mdd)


def sharpe_ratio(returns: List[float], eps: float = 1e-9) -> float:
    if not returns:
        return 0.0
    mu = sum(returns) / float(len(returns))
    var = sum((r - mu) ** 2 for r in returns) / float(max(1, len(returns) - 1))
    sd = math.sqrt(var)
    if sd < eps:
        return 0.0
    return float(mu / sd)


def build_trading_metrics_rows_with_status(
    *, ts: int, pnl_summary: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    status = _init_status("payload", "recent", "metrics")
    ps = dict(pnl_summary or {}) if isinstance(pnl_summary, dict) else {}
    if not isinstance(pnl_summary, dict):
        _mark_status(status, "payload", "trading_payload_invalid")
    recent = ps.get("recent") or []
    if not isinstance(recent, list):
        _mark_status(status, "recent", "trading_recent_invalid")
        recent = []
    rets: List[float] = []
    for r in recent[:200]:
        if not isinstance(r, dict):
            _mark_status(status, "recent", "trading_recent_item_invalid")
            continue
        realized = _safe_int(
            r.get("realized_profit_after_gas_wei"),
            0,
            status=status,
            bucket="metrics",
            code="trading_realized_invalid",
        )
        expected = _safe_int(
            r.get("expected_profit_after_costs_wei"),
            0,
            status=status,
            bucket="metrics",
            code="trading_expected_invalid",
        )
        denom = max(1, abs(expected))
        rets.append(float(realized) / float(denom))

    win_rate = _safe_float(
        ps.get("win_rate"), 0.0, status=status, bucket="metrics", code="trading_win_rate_invalid"
    )
    sr = sharpe_ratio(rets)
    dd = max_drawdown(rets)
    trades = _safe_int(
        ps.get("trades"), 0, status=status, bucket="metrics", code="trading_trades_invalid"
    )
    realized_pnl = _safe_int(
        ps.get("realized_pnl_wei"),
        0,
        status=status,
        bucket="metrics",
        code="trading_realized_pnl_invalid",
    )

    row_all = {
        "timestamp": _safe_int(
            ts, 0, status=status, bucket="metrics", code="trading_timestamp_invalid"
        ),
        "strategy_id": "ALL",
        "realized_pnl_wei": str(realized_pnl),
        "unrealized_pnl_wei": "0",
        "sharpe_ratio": float(sr),
        "win_rate": float(win_rate),
        "drawdown": float(dd),
        "trades": int(trades),
    }
    return [row_all], status


def build_trading_metrics_rows(*, ts: int, pnl_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows, _ = build_trading_metrics_rows_with_status(ts=ts, pnl_summary=pnl_summary)
    return rows


def build_treasury_metrics_row_with_status(
    *, ts: int, treasury_state: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    status = _init_status("payload", "targets", "metrics")
    t = dict(treasury_state or {}) if isinstance(treasury_state, dict) else {}
    if not isinstance(treasury_state, dict):
        _mark_status(status, "payload", "treasury_payload_invalid")
    inv = (t.get("inventory_balancer") or {}).get("targets") or {}
    if not isinstance(inv, dict):
        _mark_status(status, "targets", "treasury_targets_invalid")
        inv = {}
    ag = t.get("aggressiveness") or {}
    if not isinstance(ag, dict):
        _mark_status(status, "metrics", "treasury_aggressiveness_invalid")
        ag = {}
    governance = treasury_governance_view(t)
    goal = t.get("goal") or {}
    if not isinstance(goal, dict):
        _mark_status(status, "metrics", "treasury_goal_invalid")
        goal = {}
    row = {
        "timestamp": _safe_int(
            ts, 0, status=status, bucket="metrics", code="treasury_timestamp_invalid"
        ),
        "capital_allocations": dict(inv),
        "liquidity_buffer": _safe_float(
            (
                t.get("liquidity_buffer_pct")
                if t.get("liquidity_buffer_pct") is not None
                else goal.get("liquidity_buffer_pct")
            ),
            0.0,
            status=status,
            bucket="metrics",
            code="treasury_liquidity_buffer_invalid",
        ),
        "aggressiveness_level": str(
            governance.get("effective_aggressiveness_level")
            or ag.get("aggressiveness_level")
            or "LOW"
        ),
        "funding_rate_exposure": float(0.0),
        "reserve_ratio": _safe_float(
            inv.get("stable_reserves"),
            0.0,
            status=status,
            bucket="metrics",
            code="treasury_reserve_ratio_invalid",
        ),
        "borrow_cap_mult": _safe_float(
            governance.get("effective_borrow_mult_target_cap"),
            1.0,
            status=status,
            bucket="metrics",
            code="treasury_borrow_cap_invalid",
        ),
    }
    return row, status


def build_treasury_metrics_row(*, ts: int, treasury_state: Dict[str, Any]) -> Dict[str, Any]:
    row, _ = build_treasury_metrics_row_with_status(ts=ts, treasury_state=treasury_state)
    return row


def build_governance_metrics_row_with_status(
    *, ts: int, governance_state: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    status = _init_status("payload", "threat", "records")
    g = dict(governance_state or {}) if isinstance(governance_state, dict) else {}
    if not isinstance(governance_state, dict):
        _mark_status(status, "payload", "governance_payload_invalid")
    threat = g.get("threat") or {}
    if not isinstance(threat, dict):
        _mark_status(status, "threat", "governance_threat_invalid")
        threat = {}
    tscore = _safe_float(
        threat.get("score"),
        0.0,
        status=status,
        bucket="threat",
        code="governance_threat_score_invalid",
    )
    compliance = float(_clip(1.0 - tscore, 0.0, 1.0))
    pdr_tail = g.get("pdr_tail") or []
    if not isinstance(pdr_tail, list):
        _mark_status(status, "records", "governance_pdr_tail_invalid")
        pdr_tail = []
    override_log = g.get("override_log") or []
    if not isinstance(override_log, list):
        _mark_status(status, "records", "governance_override_log_invalid")
        override_log = []
    row = {
        "timestamp": _safe_int(
            ts, 0, status=status, bucket="records", code="governance_timestamp_invalid"
        ),
        "policy_decision_records": int(len(pdr_tail)),
        "threat_monitor_scores": float(tscore),
        "workflow_tier": str(g.get("workflow_tier") or g.get("tier") or ""),
        "compliance_score": float(compliance),
        "override_events": int(len(override_log)),
    }
    return row, status


def build_governance_metrics_row(*, ts: int, governance_state: Dict[str, Any]) -> Dict[str, Any]:
    row, _ = build_governance_metrics_row_with_status(ts=ts, governance_state=governance_state)
    return row


def build_regime_context_row_with_status(
    *, ts: int, behave_state: Dict[str, Any], market_state: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    status = _init_status("behave", "market", "metrics")
    b = dict(behave_state or {}) if isinstance(behave_state, dict) else {}
    if not isinstance(behave_state, dict):
        _mark_status(status, "behave", "regime_behave_payload_invalid")
    m = dict(market_state or {}) if isinstance(market_state, dict) else {}
    if not isinstance(market_state, dict):
        _mark_status(status, "market", "regime_market_payload_invalid")
    b_features = b.get("features") or {}
    if not isinstance(b_features, dict):
        _mark_status(status, "behave", "regime_behave_features_invalid")
        b_features = {}
    row = {
        "timestamp": _safe_int(
            ts, 0, status=status, bucket="metrics", code="regime_timestamp_invalid"
        ),
        "regime_label": str(b.get("regime_label") or b.get("regime") or "unknown"),
        "volatility_index": _safe_float(
            m.get("volatility_proxy") or b_features.get("volatility_proxy"),
            0.0,
            status=status,
            bucket="market",
            code="regime_volatility_invalid",
        ),
        "liquidity_score": _safe_float(
            b_features.get("liquidity_score"),
            0.0,
            status=status,
            bucket="behave",
            code="regime_liquidity_invalid",
        ),
        "sentiment_embedding_summary": str(b_features.get("sentiment_score") or ""),
        "confidence": _safe_float(
            b.get("confidence"),
            0.0,
            status=status,
            bucket="behave",
            code="regime_confidence_invalid",
        ),
    }
    return row, status


def build_regime_context_row(
    *, ts: int, behave_state: Dict[str, Any], market_state: Dict[str, Any]
) -> Dict[str, Any]:
    row, _ = build_regime_context_row_with_status(
        ts=ts, behave_state=behave_state, market_state=market_state
    )
    return row
