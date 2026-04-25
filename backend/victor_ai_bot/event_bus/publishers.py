from __future__ import annotations

from collections import deque
from typing import Any, Dict, List


class InMemoryEventBus:
    def __init__(self):
        self._events = deque(maxlen=1000)

    def publish(self, topic: str, key: str, payload: Dict[str, Any]) -> None:
        self._events.append({"topic": str(topic), "key": str(key), "payload": dict(payload or {})})

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self._events)
