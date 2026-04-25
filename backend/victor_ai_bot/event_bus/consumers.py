from __future__ import annotations

from typing import Any, Dict, Iterable, List


def consume_topic(events: Iterable[Dict[str, Any]], topic: str) -> List[Dict[str, Any]]:
    return [dict(e) for e in events if str((e or {}).get("topic") or "") == str(topic)]
