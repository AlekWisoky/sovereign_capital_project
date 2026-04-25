from __future__ import annotations

"""Offline replay/backtesting harness (deterministic, file-driven).

This is a lightweight framework to replay previously recorded state snapshots
(e.g., /api/admin/state JSONL dumps) and compute expected PnL under the bot's
scoring metadata.

It is intentionally conservative:
- Uses precomputed meta.safety.profit_after_costs_wei if available.
- Adjusts by brain.p_success if available.
- Does not attempt to model partial fills (tx is atomic).

The goal is to provide a foundation for deeper backtesting and regime-aware
calibration, not to claim exact realized on-chain performance.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..models import Opportunity
from ..portfolio_optimizer import opportunity_route_ready
from ..runtime_services.profitability_truth import opportunity_profit_after_costs_info

_SAFE_INT_EXCEPTIONS = (TypeError, ValueError, OverflowError)
_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError, OverflowError)
_SAFE_PARSE_EXCEPTIONS = (TypeError, ValueError, AttributeError)


def _runtime_bucket() -> Dict[str, Any]:
    return {"count": 0, "code": "", "degraded": False}


def _init_runtime_state() -> Dict[str, Any]:
    return {
        "json": _runtime_bucket(),
        "payload": _runtime_bucket(),
        "opportunity": _runtime_bucket(),
        "selection": _runtime_bucket(),
        "degraded": False,
    }


def _mark_runtime(runtime: Dict[str, Any], bucket: str, code: str) -> None:
    entry = runtime.get(bucket)
    if not isinstance(entry, dict):
        entry = _runtime_bucket()
        runtime[bucket] = entry
    entry["count"] = int(entry.get("count") or 0) + 1
    entry["code"] = str(code or "")
    entry["degraded"] = True
    runtime["degraded"] = True


def _to_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return int(default)
        if isinstance(x, bool):
            return int(default)
        return int(x)
    except _SAFE_INT_EXCEPTIONS:
        return int(default)


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        if isinstance(x, bool):
            return float(default)
        return float(x)
    except _SAFE_FLOAT_EXCEPTIONS:
        return float(default)


def _parse_opportunity(d: Dict[str, Any], *, runtime: Optional[Dict[str, Any]] = None) -> Optional[Opportunity]:
    try:
        if hasattr(Opportunity, "model_validate"):
            return Opportunity.model_validate(d)
        return Opportunity.parse_obj(d)  # type: ignore[attr-defined]
    except _SAFE_PARSE_EXCEPTIONS:
        if runtime is not None:
            _mark_runtime(runtime, "opportunity", "opportunity_parse_failed")
        return None


def _extract_opportunities(payload: Dict[str, Any], *, runtime: Optional[Dict[str, Any]] = None) -> List[Opportunity]:
    """Best-effort extraction across different snapshot shapes."""
    candidates = None
    if isinstance(payload.get("opportunities"), list):
        candidates = payload.get("opportunities")
    elif isinstance(payload.get("state"), dict) and isinstance(payload["state"].get("opportunities"), list):
        candidates = payload["state"].get("opportunities")
    elif isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("opportunities"), list):
        candidates = payload["data"].get("opportunities")
    if not isinstance(candidates, list):
        return []
    out: List[Opportunity] = []
    for it in candidates:
        if not isinstance(it, dict):
            if runtime is not None:
                _mark_runtime(runtime, "opportunity", "opportunity_candidate_invalid")
            continue
        o = _parse_opportunity(it, runtime=runtime)
        if o is not None:
            out.append(o)
    return out


def _extract_block_ts(payload: Dict[str, Any]) -> Tuple[int, int]:
    """Return (block, ts). Both default to 0 if missing."""
    block = _to_int(payload.get("block"), 0)
    ts = _to_int(payload.get("ts"), 0)
    if block == 0 and isinstance(payload.get("state"), dict):
        block = _to_int(payload["state"].get("block"), block)
        ts = _to_int(payload["state"].get("ts"), ts)
    return block, ts


def _meta_for_opp(o: Opportunity) -> Dict[str, Any]:
    meta = getattr(o, "meta", None)
    return meta if isinstance(meta, dict) else {}


def _route_id_for_opp(o: Opportunity) -> str:
    route_id = str(getattr(o, "route_id", "") or "")
    if route_id:
        return route_id
    route = getattr(o, "route", None)
    return str(getattr(route, "route_id", "") or "")


@dataclass
class BacktestTrade:
    ts: int
    block: int
    opportunity_id: str
    route_id: str
    profit_after_costs_wei: int
    p_success: float
    expected_profit_wei: int
    send_mode: str = ""


@dataclass
class BacktestReport:
    ticks: int
    trades: int
    expected_profit_wei: int
    avg_expected_profit_wei: int
    win_rate_proxy: float
    by_route: Dict[str, Dict[str, Any]]
    runtime: Dict[str, Any] = field(default_factory=_init_runtime_state)


def select_best_trade(opps: List[Opportunity], *, runtime: Optional[Dict[str, Any]] = None) -> Optional[BacktestTrade]:
    best: Optional[BacktestTrade] = None
    for o in opps:
        if not bool(getattr(o, "can_execute", True)):
            continue
        route_ready, route_reason, _route_reason_codes = opportunity_route_ready(o)
        if not bool(route_ready):
            if runtime is not None:
                _mark_runtime(runtime, "selection", str(route_reason or "selection_route_not_ready"))
            continue
        profit, verified, profit_reason = opportunity_profit_after_costs_info(o)
        if not bool(verified):
            if runtime is not None:
                _mark_runtime(
                    runtime,
                    "selection",
                    str(profit_reason or "selection_profit_after_costs_unverified"),
                )
            continue
        if int(profit) <= 0:
            continue
        meta = _meta_for_opp(o)
        brain = meta.get("brain") if isinstance(meta.get("brain"), dict) else {}
        p_success = _to_float(brain.get("p_success"), 1.0)
        p_success = max(0.0, min(1.0, p_success))
        exp_profit = int(round(float(profit) * float(p_success)))
        route_id = _route_id_for_opp(o)
        if not route_id and runtime is not None:
            _mark_runtime(runtime, "selection", "selection_route_id_missing")
        rec = BacktestTrade(
            ts=_to_int(meta.get("ts"), 0),
            block=_to_int(meta.get("block"), 0),
            opportunity_id=str(getattr(o, "id", "") or ""),
            route_id=route_id,
            profit_after_costs_wei=int(profit),
            p_success=float(p_success),
            expected_profit_wei=int(exp_profit),
            send_mode=str(meta.get("send_mode") or ""),
        )
        if best is None or rec.expected_profit_wei > best.expected_profit_wei:
            best = rec
    return best


def replay_jsonl(path: str, *, max_lines: int = 0) -> BacktestReport:
    """Replay a JSONL dump of snapshots."""
    ticks = 0
    trades: List[BacktestTrade] = []
    by_route: Dict[str, Dict[str, Any]] = {}
    runtime = _init_runtime_state()

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ticks += 1
            if max_lines and ticks > int(max_lines):
                break
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                _mark_runtime(runtime, "json", "json_decode_failed")
                continue
            if not isinstance(payload, dict):
                _mark_runtime(runtime, "payload", "payload_invalid")
                continue

            block, ts = _extract_block_ts(payload)
            opps = _extract_opportunities(payload, runtime=runtime)
            if not opps:
                continue
            best = select_best_trade(opps, runtime=runtime)
            if best is None:
                continue
            if best.block == 0:
                best.block = block
            if best.ts == 0:
                best.ts = ts
            trades.append(best)

            rid = best.route_id or "unknown"
            if rid not in by_route:
                by_route[rid] = {"trades": 0, "expected_profit_wei": 0}
            by_route[rid]["trades"] = int(by_route[rid].get("trades") or 0) + 1
            by_route[rid]["expected_profit_wei"] = int(by_route[rid].get("expected_profit_wei") or 0) + int(best.expected_profit_wei)

    total_exp = sum(int(t.expected_profit_wei) for t in trades)
    avg = int(total_exp // max(1, len(trades)))
    win_rate = float(len(trades)) / float(max(1, len(trades))) if trades else 0.0

    return BacktestReport(
        ticks=int(ticks),
        trades=int(len(trades)),
        expected_profit_wei=int(total_exp),
        avg_expected_profit_wei=int(avg),
        win_rate_proxy=float(win_rate),
        by_route=by_route,
        runtime=runtime,
    )
