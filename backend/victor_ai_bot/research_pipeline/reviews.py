from __future__ import annotations

from typing import Dict


def review_status(decision: str) -> Dict[str, str]:
    d = str(decision or 'pending').lower()
    if d not in {'approved','rejected','needs_work','pending'}:
        d = 'pending'
    return {'decision': d}
