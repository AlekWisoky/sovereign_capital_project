from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class LifecycleTransitionResult:
    success: bool
    state: str
    reason: str


class LifecycleService:
    def state(self, runtime: Any) -> Dict[str, Any]:
        fn = getattr(runtime, "evolution_state", None)
        return fn() if callable(fn) else {"ok": True, "enabled": False}
