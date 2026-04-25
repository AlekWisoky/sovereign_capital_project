from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class GroupName(str, Enum):
    STRATEGY = "Strategy Group"
    ARBITRAGE = "Arbitrage Group"
    MEV = "MEV Group"
    RISK = "Risk Group"
    KNOWLEDGE = "Knowledge Group"
    EXECUTION = "Execution Group"


class RoleName(str, Enum):
    COORDINATOR = "Coordinator Agent"
    INITIATOR = "Initiator Agent"
    EXECUTOR = "Executor Agent"
    NEGOTIATOR = "Negotiator Agent"
    OBSERVER = "Observer Agent"


class AgentState(str, Enum):
    IDLE = "IDLE"
    EVALUATING = "EVALUATING"
    NEGOTIATING = "NEGOTIATING"
    EXECUTING = "EXECUTING"
    WAITING = "WAITING"
    SUSPENDED = "SUSPENDED"
    ERROR = "ERROR"


@dataclass
class StateTransition:
    ts: float
    agent_id: str
    group: str
    role: str
    prev: str
    new: str
    reason: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentHandle:
    """Lightweight registry entry for a superstructure agent."""

    agent_id: str
    group: GroupName
    role: RoleName
    state: AgentState = AgentState.IDLE
    suspended: bool = False
    last_error: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    last_transition_ts: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "group": str(self.group.value),
            "role": str(self.role.value),
            "state": str(self.state.value),
            "suspended": bool(self.suspended),
            "last_error": str(self.last_error or ""),
            "meta": dict(self.meta or {}),
            "last_transition_ts": float(self.last_transition_ts or 0.0),
        }


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))
