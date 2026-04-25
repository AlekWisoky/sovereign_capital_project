from __future__ import annotations

from typing import Any, Dict, Iterable, List


def replay_window(events: Iterable[Dict[str, Any]], limit: int = 100) -> List[Dict[str, Any]]:
    rows = [dict(x) for x in events]
    return rows[-max(1, int(limit)):]
