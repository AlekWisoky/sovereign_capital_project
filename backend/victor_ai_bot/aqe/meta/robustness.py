from __future__ import annotations

from typing import Any, Dict, List


_SCENARIOS = [
    ('liquidity_drop_50', {'liquidity_mult': 0.50, 'gas_mult': 1.0, 'slippage_mult': 1.5, 'noise': 0.02}),
    ('gas_5x', {'liquidity_mult': 1.0, 'gas_mult': 5.0, 'slippage_mult': 1.25, 'noise': 0.01}),
    ('slippage_3x', {'liquidity_mult': 0.85, 'gas_mult': 1.0, 'slippage_mult': 3.0, 'noise': 0.02}),
    ('noise_injection', {'liquidity_mult': 0.95, 'gas_mult': 1.2, 'slippage_mult': 1.4, 'noise': 0.06}),
]



def stress_test_candidate(*, expected_profit_usd: float, gas_cost_usd: float, slippage_bps: int, liquidity_score: float, success_rate: float) -> Dict[str, Any]:
    outcomes: List[Dict[str, Any]] = []
    survivors = 0
    for name, cfg in _SCENARIOS:
        realized = expected_profit_usd
        realized *= max(0.0, min(1.0, liquidity_score * float(cfg['liquidity_mult']) + 0.25))
        realized -= gas_cost_usd * float(cfg['gas_mult'])
        realized -= expected_profit_usd * ((float(slippage_bps) / 10_000.0) * float(cfg['slippage_mult']))
        realized -= expected_profit_usd * float(cfg['noise'])
        realized *= max(0.25, min(1.0, float(success_rate)))
        passed = realized > 0.0
        if passed:
            survivors += 1
        outcomes.append({'scenario': name, 'realizedUsd': round(realized, 6), 'passed': passed})
    robust_score = float(survivors) / float(max(1, len(_SCENARIOS)))
    stage = 'paper_trading' if robust_score >= 0.75 else ('degraded' if robust_score < 0.40 else 'experimental')
    return {
        'robustness_score': round(robust_score, 6),
        'survivors': survivors,
        'scenarios': outcomes,
        'recommended_stage': stage,
    }
