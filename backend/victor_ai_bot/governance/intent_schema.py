from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from victor_ai_bot.determinism import stable_hash_int


def stable_intent_id(seed: str) -> str:
    # Deterministic id: 128-bit hex-ish
    x = stable_hash_int(f"intent:{seed}")
    return "int_" + format(int(x) & ((1 << 128) - 1), "032x")


@dataclass
class TransactionIntent:
    intent_id: str
    agent_id: str
    strategy_type: str
    objective: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_edge: float = 0.0
    risk_profile: str = "conservative"  # conservative|moderate|aggressive
    capital_allocation: float = 0.0  # percentage
    execution_constraints: Dict[str, Any] = field(default_factory=dict)
    governance_tags: Dict[str, Any] = field(default_factory=dict)
    timestamp: int = field(default_factory=lambda: int(time.time()))

    approved: bool = False
    approval_ts: int = 0
    reviewer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d
