from __future__ import annotations

from typing import Any, Dict, List

from ..models import Opportunity
from ..rpc import JsonRpcClient


class RuntimeDecisionFinalizeFacade:
    """Decision-finalization compatibility facade.

    This isolates the remaining decision-finalization chain from
    ``RuntimeBundle._loop`` while preserving existing decision, treasury
    overlay, auto-queue refresh, and post-decision analytics behavior.
    """

    async def _run_decision_finalize(
        self,
        *,
        opps: List[Opportunity],
        rpc: JsonRpcClient,
        regime_label: str,
        treasury_state: Dict[str, Any] | None,
        current_block: int,
        loop_started_at: float,
    ) -> Any:
        decision = self._safe_decide_opportunities(
            opps,
            current_block=int(current_block),
            pending_txs=int(len(self._pending)),
            auto_enabled=bool(self._auto_trading),
            gas_budget_remaining_wei=self._gas_budget_remaining_wei(),
        )

        decision = self._apply_treasury_borrow_overlay(
            decision=decision,
            treasury_state=dict(treasury_state or {}),
            regime_label=str(regime_label),
        )

        self._refresh_auto_queue_from_decision(decision, current_block=int(current_block))

        await self._run_postdecision_analytics_state(
            opps=opps,
            rpc=rpc,
            regime_label=str(regime_label or "balanced"),
            current_block=int(current_block),
            loop_started_at=float(loop_started_at),
        )
        return decision
