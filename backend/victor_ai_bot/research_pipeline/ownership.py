from __future__ import annotations

from typing import Dict


def owner_record(*, owner: str, reviewer: str = '') -> Dict[str, str]:
    return {'owner': str(owner), 'reviewer': str(reviewer)}
