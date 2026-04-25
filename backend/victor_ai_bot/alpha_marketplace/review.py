from __future__ import annotations

from typing import Dict


def review_submission(*, enabled: bool, decision: str) -> Dict[str, str]:
    if not enabled:
        return {'allowed': 'no', 'reason': 'marketplace_disabled'}
    d = str(decision or 'pending').lower()
    if d not in {'approved','rejected','pending'}:
        d = 'pending'
    return {'allowed': 'yes', 'decision': d}
