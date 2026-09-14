from __future__ import annotations

from typing import Any, Dict, List

from ..decision_identity import ensure_decision_identity
from ..models import Opportunity
from ..rpc import JsonRpcClient


class RuntimeDecisionFinalizeFacade:
    """Decision-finalization compatibility facade.

    This isolates the remaining decision-finalization chain from
    ``RuntimeBundle._loop`` while preserving existing decision, treasury
    overlay, auto-queue refresh, and post-decision analytics behavior.
    """

    def _freeze_agent_evidence_at_decision_boundary(
        self, *, decision: Any, opps: List[Opportunity], current_block: int
    ) -> Dict[str, Any]:
        if decision is None or not hasattr(self, "freeze_agent_decision_evidence"):
            return {}
        try:
            opp_id = str(getattr(decision, "opp_id", "") or "")
            candidate = next((opp for opp in list(opps or []) if str(getattr(opp, "id", "") or "") == opp_id), None)
            if candidate is None:
                return {}
            identity = ensure_decision_identity(
                candidate,
                decision,
                chain_name=str(getattr(getattr(self.cfg, "chain", None), "name", "chain") or "chain"),
                current_block=int(current_block),
            )
            metadata = dict(getattr(decision, "metadata", {}) or {})
            metadata.setdefault("canonical_decision_id", identity.decision_id)
            metadata.setdefault("correlation_id", identity.correlation_id)
            try:
                decision.metadata = metadata
            except (AttributeError, TypeError):
                return {}
            return dict(self.freeze_agent_decision_evidence(decision) or {})
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            return {}

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

        self._freeze_agent_evidence_at_decision_boundary(
            decision=decision,
            opps=list(opps or []),
            current_block=int(current_block),
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