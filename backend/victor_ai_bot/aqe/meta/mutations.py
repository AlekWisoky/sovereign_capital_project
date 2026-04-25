from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List

from .meta_learning import predict_success_probability
from .robustness import stress_test_candidate
from .structural import crossover_structures, mutate_structure
from .types import StrategyCandidate
from .regime import Regime


def _id(prefix: str, payload: str) -> str:
    h = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]
    return f"{prefix}_{h}"


def _correlation_penalty(tags: List[str], existing: List[Dict[str, Any]]) -> float:
    if not existing:
        return 0.0
    overlap = 0
    for row in existing[-20:]:
        rtags = set(row.get('feature_tags') or [])
        if rtags.intersection(tags):
            overlap += 1
    return min(0.35, overlap / max(1.0, len(existing[-20:])) * 0.35)


def _diversity_bonus(tags: List[str], existing: List[Dict[str, Any]]) -> float:
    if not existing:
        return 0.12
    seen = set()
    for row in existing[-50:]:
        for tag in list(row.get('feature_tags') or []):
            seen.add(str(tag))
    unseen = len([t for t in tags if t not in seen])
    return min(0.18, unseen * 0.05)


def propose_candidates(*, regime: Regime, telemetry: Dict[str, Any], bounds: Dict[str, Any], existing: List[Dict[str, Any]] | None = None) -> List[StrategyCandidate]:
    now = time.time()
    out: List[StrategyCandidate] = []
    existing = list(existing or [])
    basefee = float(telemetry.get('basefee_gwei') or 0.0)
    opp_rate = float(telemetry.get('opportunity_rate') or 0.0)
    sr = float(telemetry.get('success_rate') or 0.0)
    gross_profit_usd = float(telemetry.get('expected_profit_usd') or max(2.0, opp_rate * 2.0))
    gas_cost_usd = float(telemetry.get('gas_cost_usd') or max(0.5, basefee * 0.03))
    slippage_bps = int(telemetry.get('slippage_bps') or 50)
    liquidity_score = max(0.1, min(1.0, 1.0 - float(telemetry.get('route_fail_rate') or 0.0)))

    base_structure = (existing[-1].get('structure_patch') if existing else {}) or {}
    structural = mutate_structure(f"{regime.name}:{opp_rate}:{sr}:{basefee}", base_structure, regime.name)
    meta_prob = predict_success_probability(regime=regime.name, structure=structural, memory_rows=existing)
    stress = stress_test_candidate(expected_profit_usd=gross_profit_usd, gas_cost_usd=gas_cost_usd, slippage_bps=slippage_bps, liquidity_score=liquidity_score, success_rate=max(0.2, sr))
    feature_tags = sorted(set([regime.name] + list(structural.get('signals') or [])))
    corr_penalty = _correlation_penalty(feature_tags, existing)
    diversity_bonus = _diversity_bonus(feature_tags, existing)
    novelty_score = max(0.0, min(1.0, 0.35 + diversity_bonus - corr_penalty))

    scenarios: List[tuple[str, Dict[str, Any], Dict[str, Any], str, str]] = []
    if regime.name in {'high_volatility', 'bear'}:
        scenarios.append((
            'High volatility structural tighten',
            {'gas_mode': 'fast' if basefee < 60 else 'standard', 'send_mode': 'protected_rpc', 'trade_cooldown_blocks': int(max(1, bounds.get('min_trade_cooldown', 2)))},
            {'require_simulation': True, 'slippage_bps': int(min(bounds.get('max_slippage_bps', 120), 85))},
            'volatility_proxy high',
            'defensive_atomic',
        ))
    if regime.name in {'gas_spike', 'low_liquidity'}:
        scenarios.append((
            'High gas / low liquidity resilience',
            {'send_mode': 'private' if bounds.get('allow_private', True) else 'protected_rpc', 'gas_mode': 'standard', 'max_submit_per_block': 1},
            {'minProfitAbs': str(int(str(telemetry.get('minProfitAbs') or '0')) + int(bounds.get('min_profit_abs_bump_wei', 2 * 10**15))), 'require_simulation': True},
            'gas or liquidity stress',
            'small_size_atomic',
        ))
    if regime.name in {'balanced', 'bull', 'low_volatility'} and sr >= 0.55:
        scenarios.append((
            'Opportunity rich throughput',
            {'gas_mode': 'fast' if basefee < 40 else 'standard', 'max_submit_per_block': int(min(2, bounds.get('max_submit_per_block', 2)))},
            {'minProfitBps': int(min(int(telemetry.get('minProfitBps') or 0) + 5, int(bounds.get('max_min_profit_bps', 80))))},
            'healthy fill rate',
            'durable_atomic',
        ))

    if len(existing) >= 2:
        left = existing[-1].get('structure_patch') or {}
        right = existing[-2].get('structure_patch') or {}
        structural_cross = crossover_structures(f"xover:{regime.name}:{len(existing)}", left, right)
        scenarios.append((
            'Gene crossover candidate',
            {'gas_mode': 'standard', 'max_submit_per_block': 1},
            {'require_simulation': True},
            'novel crossover',
            'hybrid_atomic',
        ))
    else:
        structural_cross = structural

    for idx, (desc, settings_patch, safety_patch, reason, family) in enumerate(scenarios[: max(1, int(bounds.get('max_candidates', 5)) - 1)]):
        structure_patch = structural if idx % 2 == 0 else structural_cross
        struct_tags = sorted(set(feature_tags + list(structure_patch.get('signals') or [])))
        cp = _correlation_penalty(struct_tags, existing)
        db = _diversity_bonus(struct_tags, existing)
        robust = stress if idx % 2 == 0 else stress_test_candidate(expected_profit_usd=gross_profit_usd * 1.05, gas_cost_usd=gas_cost_usd, slippage_bps=max(10, slippage_bps - 5), liquidity_score=liquidity_score, success_rate=max(0.2, sr))
        score = max(0.05, min(0.95, (0.35 * meta_prob) + (0.25 * robust['robustness_score']) + (0.20 * sr) + db - cp))
        payload = f"{regime.name}:{desc}:{settings_patch}:{safety_patch}:{structure_patch}"
        out.append(StrategyCandidate(
            id=_id('meta', payload),
            created_ts=now,
            description=desc,
            score=float(score),
            settings_patch=settings_patch,
            safety_patch=safety_patch,
            regime=regime.name,
            reason=reason,
            strategy_family=family,
            lifecycle_stage=str(robust.get('recommended_stage') or 'experimental'),
            parent_ids=[str(existing[-1].get('id'))] if existing else [],
            genealogy_depth=int((existing[-1].get('genealogy_depth') or 0) + 1) if existing else 0,
            regime_tags=[regime.name],
            feature_tags=struct_tags,
            structure_patch=structure_patch,
            mutation_history=list(structure_patch.get('mutation_history') or []),
            stress_report=robust,
            meta_success_probability=float(meta_prob),
            diversity_bonus=float(db),
            correlation_penalty=float(cp),
            novelty_score=float(max(0.0, min(1.0, 0.30 + db - cp))),
        ))

    payload = f"{regime.name}:noop"
    out.append(StrategyCandidate(
        id=_id('meta', payload),
        created_ts=now,
        description='No-op baseline (for comparison)',
        score=0.10,
        settings_patch={},
        safety_patch={},
        regime=regime.name,
        reason='baseline',
        strategy_family='flashloan_atomic',
        lifecycle_stage='experimental',
        regime_tags=[regime.name],
        feature_tags=['baseline', regime.name],
        structure_patch={'signals': ['spread'], 'entry_logic': 'spread > threshold', 'exit_logic': 'exit_on_min_profit', 'timing_model': 'instant'},
        mutation_history=['baseline'],
        stress_report=stress,
        meta_success_probability=0.50,
        diversity_bonus=0.0,
        correlation_penalty=0.0,
        novelty_score=0.0,
    ))

    out.sort(key=lambda x: (float(x.score), float(x.novelty_score), -float(x.correlation_penalty)), reverse=True)
    k = int(bounds.get('max_candidates', 5))
    return out[:k]
