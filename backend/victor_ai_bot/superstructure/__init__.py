"""AUTONOMOUS_QUANT_AI_MODE_VΩ_SUPERSTRUCTURE (add-only).

This package layers an Agent-Group-Role (AGR) organizational model +
negotiation-driven execution gating on top of the existing CAQ-KDS + SMMAE engine.

Hard constraints:
  - Does not modify core command semantics.
  - Backward compatible: disabled by default.
  - Purely additive: orchestrates existing engines via optional hooks.
"""

from .types import AgentState, GroupName, RoleName
from .runtime import SuperstructureRuntime

__all__ = [
    "AgentState",
    "GroupName",
    "RoleName",
    "SuperstructureRuntime",
]
