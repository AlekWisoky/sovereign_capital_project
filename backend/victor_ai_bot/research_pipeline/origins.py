from __future__ import annotations

from typing import Dict


def normalize_origin(origin: str) -> Dict[str, str]:
    o = str(origin or 'ai').lower()
    if o not in {'human','ai','hybrid','marketplace'}:
        o = 'ai'
    return {'origin': o, 'hybrid': 'yes' if o == 'hybrid' else 'no'}
