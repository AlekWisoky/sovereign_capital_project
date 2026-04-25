from __future__ import annotations

from typing import Any, Dict, List


FAMILY_SEQUENCE = ['flashloan_atomic', 'liquidation_anticipation', 'oracle_drift', 'liquidity_migration', 'volatility_event_overlay']


def assign_candidate_family(*, candidate: Dict[str, Any], regime: str) -> Dict[str, Any]:
    seed = str(candidate.get('id') or candidate.get('description') or '')
    idx = sum(ord(ch) for ch in seed + str(regime)) % len(FAMILY_SEQUENCE)
    fam = FAMILY_SEQUENCE[idx]
    c = dict(candidate)
    c['strategy_family'] = fam
    c['family_reason'] = f'regime_seeded:{regime}:{idx}'
    return c


def overlap_penalty(*, candidate: Dict[str, Any], existing_rows: List[Dict[str, Any]]) -> float:
    fam = str(candidate.get('strategy_family') or '')
    overlaps = sum(1 for row in list(existing_rows or [])[-100:] if str(row.get('strategy_family') or '') == fam)
    return round(min(0.30, overlaps * 0.015), 6)
