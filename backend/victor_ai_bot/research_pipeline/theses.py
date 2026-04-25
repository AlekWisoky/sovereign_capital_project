from __future__ import annotations

from typing import Dict


def thesis_record(*, title: str, body: str, owner: str, family: str) -> Dict[str, str]:
    return {'title': str(title), 'body': str(body), 'owner': str(owner), 'family': str(family)}
