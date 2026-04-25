from __future__ import annotations

from typing import Any, Dict, List

from victor_ai_bot.determinism import stable_hash_int


_SIGNAL_POOL = ['spread', 'volatility_proxy', 'gas_pressure', 'mev_risk', 'liquidity_fragility', 'latency_half_life', 'venue_quality']
_ENTRY_RULES = [
    'spread > threshold',
    'spread > threshold AND volatility_proxy > 0.35',
    'spread > threshold AND gas_pressure < 0.65',
    'spread > threshold AND venue_quality > 0.55',
]
_EXIT_RULES = [
    'exit_on_min_profit',
    'exit_on_min_profit OR timeout',
    'exit_on_slippage_breaker',
]
_TIMING_MODELS = ['instant', 'confirm_same_block', 'latency_windowed']



def deterministic_gene(seed: str, base: Dict[str, Any]) -> Dict[str, Any]:
    idx = stable_hash_int(seed, 10_000)
    entry = _ENTRY_RULES[idx % len(_ENTRY_RULES)]
    exit_rule = _EXIT_RULES[(idx // 7) % len(_EXIT_RULES)]
    timing = _TIMING_MODELS[(idx // 13) % len(_TIMING_MODELS)]
    ordered_signals = sorted(_SIGNAL_POOL, key=lambda x: stable_hash_int(seed + ':' + x, 1_000_000))
    signal_count = 3 + (idx % 2)
    signals = ordered_signals[:signal_count]
    return {
        'signals': signals,
        'entry_logic': entry,
        'exit_logic': exit_rule,
        'timing_model': timing,
        'risk_model': str(base.get('risk_model') or 'bounded_atomic'),
        'execution_pattern': str(base.get('execution_pattern') or 'capture_first'),
    }



def mutate_structure(seed: str, parent: Dict[str, Any], regime: str) -> Dict[str, Any]:
    parent_gene = dict(parent or {})
    gene = deterministic_gene(seed + ':' + regime, parent_gene)
    mutation_history: List[str] = []
    if parent_gene:
        if gene.get('entry_logic') != parent_gene.get('entry_logic'):
            mutation_history.append('change_entry_rule')
        if gene.get('exit_logic') != parent_gene.get('exit_logic'):
            mutation_history.append('change_exit_rule')
        if gene.get('timing_model') != parent_gene.get('timing_model'):
            mutation_history.append('change_timing')
        parent_signals = set(parent_gene.get('signals') or [])
        new_signals = set(gene.get('signals') or [])
        if new_signals - parent_signals:
            mutation_history.append('add_signal')
        if parent_signals - new_signals:
            mutation_history.append('remove_signal')
    else:
        mutation_history.extend(['seed_structure'])
    gene['mutation_history'] = mutation_history
    return gene



def crossover_structures(seed: str, left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    idx = stable_hash_int(seed, 10_000)
    signals = sorted(set((left.get('signals') or [])[:2] + (right.get('signals') or [])[:2]))
    entry = left.get('entry_logic') if idx % 2 == 0 else right.get('entry_logic')
    exit_rule = right.get('exit_logic') if idx % 3 == 0 else left.get('exit_logic')
    timing = left.get('timing_model') if idx % 5 == 0 else right.get('timing_model')
    return {
        'signals': signals[:4],
        'entry_logic': entry,
        'exit_logic': exit_rule,
        'timing_model': timing,
        'risk_model': left.get('risk_model') or right.get('risk_model') or 'bounded_atomic',
        'execution_pattern': left.get('execution_pattern') or right.get('execution_pattern') or 'capture_first',
        'mutation_history': ['crossover'],
    }
