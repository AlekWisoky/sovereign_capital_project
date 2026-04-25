from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List


_SAFE_PDR_APPEND_EXCEPTIONS = (OSError, TypeError, ValueError)


class PolicyDecisionRecordLog:
    """Append-only Policy Decision Record (PDR) logger."""

    def __init__(self, *, path: str):
        self.path = str(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._tail: List[Dict[str, Any]] = []

    def append(self, entry: Dict[str, Any]) -> None:
        try:
            payload = dict(entry)
            payload.setdefault("ts", int(time.time()))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._tail.append(payload)
            if len(self._tail) > 500:
                self._tail = self._tail[-500:]
        except _SAFE_PDR_APPEND_EXCEPTIONS:
            return

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        return list(self._tail[-max(1, int(n)) :])
