from __future__ import annotations

from typing import Any, Dict, List

from ..identity import attach_identity, identity_from, new_decision_identity
from ..models import Opportunity
from ..rpc import JsonRpcClient


class RuntimeDecisionFinalizeFacade:
    """Decision-finalization compatibility facade.

    This isolates the remaining decision-finalization chain from
    ``RuntimeBundle._loop`` while preserving existing decision, treasury
    overlay, auto-queue refresh, and post-decision analytics behavior.
    """

    def _ensure_decision_identity(self, decision: Any, *, opps: List[Opportunity]) -> Any:
        """Make lifecycle identity explicit at the canonical decision boundary."""
        if decision is None:
            return decision
        existing = identity_from(decision)
        identity = (
            existing
            if existing is not None and existing.decision_id and existing.correlation_id
            else new_decision_identity()
        )
        attach_identity(decision, identity)
        try:
            metadata = getattr(decision, "metadata", None)
            if isinstance(metadata, dict):
                metadata.setdefault("identity", {}).update(identity.to_dict())
                metadata.setdefault("decision_context", {}).update(
                    {"candidate_count": int(len(opps or []))}
                )
        except (AttributeError, TypeError, ValueError):
            pass
        return decision

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
        decision = self._ensure_decision_identity(decision, opps=opps)

        decision = self._apply_treasury_borrow_overlay(
            decision=decision,
            treasury_state=dict(treasury_state or {}),
            regime_label=str(regime_label),
        )
        # Treasury overlays may return a replacement decision object. Reuse the
        # existing lineage whenever it survived the overlay; otherwise the
        # overlay metadata is the recovery source. Do not create a second
        # identity when the original is recoverable.
        identity = identity_from(decision)
        if identity is None or not identity.decision_id or not identity.correlation_id:
            identity = identity_from(getattr(decision, "metadata", {})) or new_decision_identity()
        attach_identity(decision, identity)

        self._refresh_auto_queue_from_decision(decision, current_block=int(current_block))

        await self._run_postdecision_analytics_state(
            opps=opps,
            rpc=rpc,
            regime_label=str(regime_label or "balanced"),
            current_block=int(current_block),
            loop_started_at=float(loop_started_at),
        )
        return decision
