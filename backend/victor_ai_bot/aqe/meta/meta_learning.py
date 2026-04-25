from __future__ import annotations

from typing import Any, Dict, Iterable, List


def predict_success_probability(*, regime: str, structure: Dict[str, Any], memory_rows: List[Dict[str, Any]]) -> float:
    if not memory_rows:
        return 0.55
    hits = 0
    wins = 0
    sigs = set(structure.get('signals') or [])
    for row in memory_rows:
        tags = set(row.get('regime_tags') or [])
        row_sigs = set(((row.get('structure_patch') or {}).get('signals') or []))
        if regime in tags or sigs.intersection(row_sigs):
            hits += 1
            if str(row.get('lifecycle_stage') or '') in {'production', 'paper_trading'}:
                wins += 1
    if hits <= 0:
        return 0.55
    return max(0.25, min(0.95, float(wins) / float(hits)))
