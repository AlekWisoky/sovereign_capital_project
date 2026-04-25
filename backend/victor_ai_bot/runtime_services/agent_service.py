from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class AgentEvaluationResult:
    success: bool
    state: str
    details: Dict[str, Any]


class AgentService:
    def state(self, runtime: Any) -> Dict[str, Any]:
        return runtime.agent_hub_state()

    def attribution(self, runtime: Any) -> Dict[str, Any]:
        return runtime.agent_attribution_state()
