from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class OrchestratorMode(str, Enum):
    """Execution modes.

    NOTE: The core engine is still the only component that actually submits
    on-chain flashloan transactions. The orchestrator produces *plans*.
    """

    ATOMIC_FLASHLOAN = "atomic_flashloan"
    PARALLEL_CROSS_VENUE = "parallel_cross_venue"
    INVENTORY_BASED = "inventory_based"  # placeholder
    HEDGE_TRANSFER = "hedge_transfer"  # placeholder


@dataclass
class ExecutionPlan:
    mode: OrchestratorMode
    intent_id: str
    created_ts: int = field(default_factory=lambda: int(time.time()))
    # Plan knobs (execution still goes through the core path)
    size_mult: float = 1.0
    borrow_mult: float = 1.0
    gas_mode: str = "standard"

    # On-chain guardrails (core contract enforces minProfit)
    min_profit_wei: int = 0
    deadline_ts: int = 0

    # Optional extra info for non-flashloan modes
    legs: Optional[list[dict]] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class ExecutionOrchestrator:
    """Phase 4: Execution Orchestrator.

    This class routes high-level intents to a concrete execution plan.
    It must never bypass the core engine.
    """

    def __init__(self, *, allow_live: bool = False):
        self.allow_live = bool(allow_live)
        self.last_plan: Dict[str, Any] = {}

    def validate_profit(self, *, expected_profit_wei: int, min_profit_wei: int) -> bool:
        return int(expected_profit_wei) >= int(min_profit_wei)

    def route_trade(
        self,
        *,
        intent_id: str,
        expected_profit_wei: int,
        min_profit_wei: int,
        gas_mode: str,
        size_mult: float,
        borrow_mult: float,
        deadline_seconds: int = 30,
    ) -> ExecutionPlan:
        # Mode 1 is the default for this project.
        plan = ExecutionPlan(
            mode=OrchestratorMode.ATOMIC_FLASHLOAN,
            intent_id=str(intent_id),
            gas_mode=str(gas_mode or "standard"),
            size_mult=float(size_mult),
            borrow_mult=float(borrow_mult),
            min_profit_wei=int(min_profit_wei),
            deadline_ts=int(time.time()) + int(deadline_seconds),
        )
        plan.meta.update({"expected_profit_wei": int(expected_profit_wei)})
        plan.meta.update({"profit_ok": bool(self.validate_profit(expected_profit_wei=int(expected_profit_wei), min_profit_wei=int(min_profit_wei)))})
        self.last_plan = {"ts": int(time.time()), "plan": plan.meta, "mode": plan.mode.value}
        return plan

    def hedge_position(self, *args, **kwargs) -> Dict[str, Any]:
        # Placeholder for Phase 2+.
        return {"ok": False, "reason": "hedge_position_placeholder"}

    def rebalance_inventory(self, *args, **kwargs) -> Dict[str, Any]:
        # Placeholder for Phase 2+.
        return {"ok": False, "reason": "rebalance_inventory_placeholder"}
