from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Mapping

from .memory import StrategyMemory
from .registry import MetaRegistry
from .regime import detect_regime
from .mutations import propose_candidates
from .types import MetaState
from .predictor import predict_candidate_success
from .family_generation import assign_candidate_family, overlap_penalty
from victor_ai_bot.evolution import GenealogyStore, diversity_score, validate_multi_regime, next_stage, retirement_reason
from victor_ai_bot.portfolio_optimizer import opportunity_route_ready
from victor_ai_bot.runtime_services.profitability_truth import opportunity_profit_after_costs_info
from victor_ai_bot.profitability_projection import profitability_summary_projection


_SAFE_META_RUNTIME_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)
_SAFE_META_SETTINGS_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except _SAFE_META_RUNTIME_EXCEPTIONS:
        return int(default)


def _telemetry_route_profit_ready(opp: Any) -> bool:
    if opp is None:
        return False
    if not bool(getattr(opp, 'can_execute', False)):
        return False
    route_ready, _reason, _reason_codes = opportunity_route_ready(opp)
    if not bool(route_ready):
        return False
    profit_after, verified, _profit_reason = opportunity_profit_after_costs_info(opp)
    return bool(verified and profit_after > 0)


def _telemetry_opportunity_sort_key(opp: Any) -> tuple[int, int, str]:
    profit_after, verified, _profit_reason = opportunity_profit_after_costs_info(opp)
    if not bool(verified and profit_after > 0):
        return (0, 0, str(getattr(opp, 'id', '') or ''))
    return (1, int(profit_after), str(getattr(opp, 'id', '') or ''))


def _best_telemetry_opportunity(opps: List[Any]) -> Any | None:
    eligible = [o for o in list(opps or []) if _telemetry_route_profit_ready(o)]
    if not eligible:
        return None
    return max(eligible, key=_telemetry_opportunity_sort_key)


class MetaStrategyRuntime:
    """Deterministic meta-strategy runtime with structural evolution metadata.

    It proposes bounded structural overlays, stages them through lifecycles, and
    applies only conservative config patches through existing runtime setters.
    """

    def __init__(self, *, chain_name: str, data_dir: str, cfg: Any, allow_auto_apply: bool = False):
        self.chain_name = chain_name
        self.cfg = cfg
        self.allow_auto_apply = bool(allow_auto_apply)
        reg_path = os.path.join(data_dir, 'meta', f'meta_registry_{chain_name}.json')
        mem_path = os.path.join(data_dir, 'meta', f'meta_memory_{chain_name}.json')
        self.registry = MetaRegistry(reg_path, max_items=int(getattr(cfg, 'max_registry_items', 200)))
        self.memory = StrategyMemory(mem_path, max_items=max(400, int(getattr(cfg, 'max_registry_items', 200) * 2)))
        self.genealogy = GenealogyStore(os.path.join(data_dir, 'meta', f'meta_genealogy_{chain_name}.json'), max_items=max(400, int(getattr(cfg, 'max_registry_items', 200) * 2)))
        self.enabled = bool(getattr(cfg, 'enabled', False))
        self.mode = str(getattr(cfg, 'mode', 'observe'))
        self.tick_seconds = float(getattr(cfg, 'tick_seconds', 10.0))
        self._running = False
        self._last_tick = 0.0
        self._last_regime = 'unknown'
        self._last_actions: Dict[str, Any] = {}
        self._last_candidates: List[Dict[str, Any]] = []

    def start(self) -> None:
        if self.enabled:
            self._running = True

    async def stop(self) -> bool:
        self._running = False
        return True

    def state(self) -> Dict[str, Any]:
        data = MetaState(
            enabled=bool(self.enabled),
            mode=str(self.mode),
            last_tick_ts=float(self._last_tick),
            last_regime=str(self._last_regime),
            last_actions=dict(self._last_actions),
            last_candidates=list(self._last_candidates),
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
        top = opps[0] if opps else None
        if top is None:
            top = _best_telemetry_opportunity(opps)
        if top is not None:
            meta = _mapping(getattr(top, 'meta', {}) or {})
            unit = _mapping(meta.get('unit_econ') or {})
            projection = profitability_summary_projection(top)
            expected_profit_usd = float(projection.get('displayExpectedProfitUsd') or 0.0)
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
            'min_profit_bps_step': int(getattr(self.cfg, 'min_profit_bps_step', 10)),
            'max_min_profit_bps': int(getattr(self.cfg, 'max_min_profit_bps', 80)),
            'max_submit_per_block': int(getattr(self.cfg, 'max_submit_per_block', 2)),
            'min_trade_cooldown': int(getattr(self.cfg, 'min_trade_cooldown', 2)),
            'allow_private': bool(getattr(self.cfg, 'allow_private', True)),
        }
        rows = self.memory.load()
        cands = propose_candidates(regime=regime, telemetry=telemetry, bounds=bounds, existing=rows)
        out = []
        validation_regimes = ['balanced', 'high_volatility', 'low_volatility', 'bear']
        for c in cands:
            row = c.to_dict()
            row = assign_candidate_family(candidate=row, regime=regime.name)
            div = diversity_score(signals=((row.get('structure_patch') or {}).get('signals') or []), existing=rows, regime=regime.name)
            val = validate_multi_regime(candidate=row, regimes=validation_regimes)
            robust = float((row.get('stress_report') or {}).get('robustness_score') or 0.0)
            row['diversity_metrics'] = div
            row['validation'] = val
            row['overlap_penalty'] = overlap_penalty(candidate=row, existing_rows=rows)
            row['prediction'] = predict_candidate_success(candidate=row, memory_rows=rows, regime=regime.name)
            row['lifecycle_stage'] = next_stage(robustness=robust, validation_ok=bool(val.get('passed')), live_ok=robust >= 0.75 and float((row.get('prediction') or {}).get('predicted_success') or 0.0) >= 0.6)
            row['retirement_reason'] = retirement_reason(robustness=robust, realized_edge_usd=float(row.get('score') or 0.0), overlap_penalty=float(div.get('correlation_penalty') or 0.0) + float(row.get('overlap_penalty') or 0.0), regime_fit=max(0.0, min(1.0, float((1.0 if regime.name in set(row.get('regime_tags') or []) else 0.5)))))
            out.append(row)
            self.registry.append(c)
            self.memory.append(row)
            self.genealogy.append({'id': row.get('id'), 'parent_ids': list(row.get('parent_ids') or []), 'mutation_history': list(row.get('mutation_history') or []), 'generation_number': int(row.get('genealogy_depth') or 0), 'lifecycle_stage': row.get('lifecycle_stage'), 'retirement_reason': row.get('retirement_reason'), 'strategy_family': row.get('strategy_family')})
        self._last_candidates = out
        return out

    def apply_candidate(self, rt: Any, cand_id: str) -> Dict[str, Any]:
        cand = self.registry.get(cand_id)
        if not cand:
            return {'ok': False, 'error': 'candidate_not_found'}
        settings_patch = dict(cand.get('settings_patch') or {})
        safety_patch = dict(cand.get('safety_patch') or {})
        if 'auto_trading' in settings_patch and bool(settings_patch.get('auto_trading')):
            settings_patch['auto_trading'] = False
        try:
            if settings_patch:
                rt.set_settings(**settings_patch)
            if safety_patch and hasattr(rt, 'set_safety'):
                rt.set_safety(**safety_patch)
            else:
                s = rt.cfg.safety
                for k, v in safety_patch.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
        except _SAFE_META_SETTINGS_EXCEPTIONS as e:
            return {'ok': False, 'error': 'apply_failed', 'detail': str(e)}
        stage = str(cand.get('lifecycle_stage') or 'paper_trading')
        self.registry.mark_stage(cand_id, stage)
        self._last_actions = {
            'applied': cand_id,
            'settings_patch': settings_patch,
            'safety_patch': safety_patch,
            'structure_patch': cand.get('structure_patch') or {},
            'lifecycle_stage': stage,
        }
        return {'ok': True, 'applied': cand_id, 'lifecycle_stage': stage, 'structure_patch': cand.get('structure_patch') or {}, 'stress_report': cand.get('stress_report') or {}}

    async def tick(self, rt: Any) -> None:
        if not (self.enabled and self._running):
            return
        now = time.time()
        if now - self._last_tick < self.tick_seconds:
            return
        self._last_tick = now
        if self.mode in ('suggest', 'auto'):
            cands = self.generate(rt)
            if self.mode == 'auto' and self.allow_auto_apply:
                best = None
                for x in cands:
                    if 'No-op' in str(x.get('description')):
                        continue
                    if str(x.get('lifecycle_stage') or '') == 'degraded':
                        continue
                    best = x
                    break
                if best:
                    self.apply_candidate(rt, str(best.get('id')))
