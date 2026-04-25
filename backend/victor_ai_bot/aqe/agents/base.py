from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol


@dataclass
class AgentOutput:
    """Output of an individual agent.

    Backward-compatibility:
      - Existing fields remain and are still used by SMMAE mixers.
      - New fields (`signal`, `features_used`, `reasoning`) are additive.

    Required by AUTONOMOUS_QUANT_AI_MODE_VΩ_EXTENDED:
      - `signal` in [-1, +1]
      - `confidence` in [0, 1]
      - `reasoning` metadata (human+machine readable)
      - `features_used` logs the features that drove the signal
      - modular + replaceable + RL-adaptable
    """

    # Core SMMAE fields (Phase 1-4)
    pi_team: Dict[str, float]
    pi_self: Dict[str, float]
    alpha: float
    q_values: Dict[str, float]
    confidence: float
    info: Dict[str, Any]

    # Additive domain-signal fields
    signal: float = 0.0  # [-1, +1]
    features_used: Dict[str, Any] = field(default_factory=dict)
    reasoning: Dict[str, Any] = field(default_factory=dict)


class Agent(Protocol):
    name: str

    def act(self, *, state: Dict[str, Any]) -> AgentOutput:
        ...
