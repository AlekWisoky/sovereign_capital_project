from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

from .models import MetaCandidate, MetaMemory
from .regime import detect_regime
from ...profitability_projection import profitability_summary_projection

_SAFE_META_RUNTIME_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError, OSError)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _telemetry_route_profit_ready(opp: Any) -> bool:
    projection = profitability_summary_projection(opp)
    return bool(projection.get("valid") and projection.get("positive"))


def _telemetry_profit_rank(opp: Any) -> tuple[int, int, str]:
    meta = _mapping(getattr(opp, "meta", {}) or {})
    safety = _mapping(meta.get("safety") or {})
    try:
        profit_after = int(safety.get("profit_after_costs_wei") or 0)
    except (TypeError, ValueError):
        profit_after = 0
    return (1, int(profit_after), str(getattr(opp, "id", "") or ""))


def _best_telemetry_opportunity(opps: List[Any]) -> Any | None:
    eligible = [o for o in list(opps or []) if _telemetry_route_profit_ready(o)]
    if not eligible:
        return None
    return max(eligible, key=_telemetry_profit_rank)


class MetaStrategyRuntime:
    def __init__(self, chain_name: str, data_dir: str, cfg: Any):
        self.chain_name = chain_name
        self.data_dir = data_dir
        self.cfg = cfg
        self.memory = MetaMemory(data_dir=data_dir, chain=chain_name)
        self.genealogy = MetaMemory(data_dir=data_dir, chain=f"{chain_name}_genealogy")
        self._last_actions: List[Dict[str, Any]] = []
        self._last_candidates: List[Dict[str, Any]] = []
        self._last_regime = "unknown"

    def state(self) -> Dict[str, Any]:
        data = MetaCandidate(
            regime=self._last_regime,
            actions=list(self._last_actions),
            candidates=list(self._last_candidates),
            memory_summary=self.memory.summary(),
        ).to_dict()
        data['genealogy'] = {'recent': self.genealogy.load()[-20:]}
        return data

    def _telemetry_from_runtime(self, rt: Any) -> Dict[str, Any]:
        metrics = rt.metrics_state() if hasattr(rt, 'metrics_state') else {}
        opps = list(getattr(rt, '_opps', []) or [])
        gas_cost_usd = 0.0
        expected_profit_usd = 0.0
        route_fail_rate = 0.0
        top = _best_telemetry_opportunity(opps)
        gas_source = top if top is not None else (opps[0] if opps else None)
        if top is not None:
            projection = profitability_summary_projection(top)
            expected_profit_usd = float(projection.get('displayExpectedProfitUsd') or 0.0)
        if gas_source is not None:
            meta = _mapping(getattr(gas_source, 'meta', {}) or {})
            unit = _mapping(meta.get('unit_econ') or {})
            gas_cost_usd = float(unit.get('gas_cost_usd_micro') or 0.0)
            if gas_cost_usd > 1000.0:
                gas_cost_usd /= 1_000_000.0
        try:
            route_fail_rate = float(rt._route_fail_rate())
        except _SAFE_META_RUNTIME_EXCEPTIONS:
            route_fail_rate = 0.0
        safety = {}
        try:
            s = rt.cfg.safety
            safety = {'minProfitAbs': getattr(s, 'minProfitAbs', '0'), 'minProfitBps': getattr(s, 'minProfitBps', 0), 'slippage_bps': getattr(s, 'slippage_bps', 50)}
        except _SAFE_META_RUNTIME_EXCEPTIONS:
            safety = {}
        scan_ms = float(metrics.get('scan_ms') or 0.0)
        fail_streak = float(metrics.get('fail_streak') or 0.0)
        vol_proxy = min(1.0, 0.15 * fail_streak + min(0.4, scan_ms / 1500.0))
        return {
            **safety,
            'volatility_proxy': vol_proxy,
            'basefee_gwei': float(metrics.get('basefee_gwei') or 0.0),
            'success_rate': float(metrics.get('success_rate') or 0.0),
            'opportunity_rate': float(metrics.get('opportunity_rate') or 0.0),
            'efficiency_pct': float(metrics.get('efficiency_pct') or 0.0),
            'realized_profit_raw': str(metrics.get('realized_profit_raw') or '0'),
            'expected_profit_usd': float(expected_profit_usd),
            'gas_cost_usd': float(gas_cost_usd),
            'route_fail_rate': float(route_fail_rate),
        }

    def generate(self, rt: Any) -> List[Dict[str, Any]]:
        telemetry = self._telemetry_from_runtime(rt)
        regime = detect_regime(telemetry)
        self._last_regime = regime.name
        bounds = {
            'max_candidates': int(getattr(self.cfg, 'max_candidates', 5)),
            'max_slippage_bps': int(getattr(self.cfg, 'max_slippage_bps', 120)),
            'min_profit_abs_bump_wei': int(getattr(self.cfg, 'min_profit_abs_bump_wei', 2 * 10**15)),
        }
        return []
