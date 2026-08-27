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

    @staticmethod
    def _ensure_decision_identity(decision: Any, *, opps: List[Opportunity]) -> Any:
        """Make lifecycle identity explicit at the canonical decision boundary.

        Identity is created once for the decision and then carried unchanged
        through treasury overlays, execution, settlement, and OMAR learning.
        A skip is still a real decision and therefore receives an identity.
        """
        if decision is None:
            return decision
        existing = identity_from(decision)
        if existing is None or not existing.decision_id or not existing.correlation_id:
            identity = new_decision_identity()
        else:
            identity = existing
        attach_identity(decision, identity)

        # Preserve useful decision context beside the identity without making
        # identity generation depend on mutable opportunity metadata.
        try:
            metadata = getattr(decision, "metadata", None)
            if isinstance(metadata, dict):
                metadata.setdefault("identity", {}).update(identity.to_dict())
                metadata.setdefault("decision_context", {})
                metadata["decision_context"].update(
                    {
                        "chain": str(getattr(self, "chain", "") or ""),
                        "candidate_count": int(len(opps or [])),
                    }
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
        # Treasury overlays may return a replacement decision object. Re-attach
        # the original identity rather than creating a second decision lineage.
        identity = identity_from(decision)
        if identity is None or not identity.decision_id or not identity.correlation_id:
            # The canonical identity was already created above. Recover it from
            # the selected decision metadata when an overlay replaced the object.
            identity = identity_from(
                getattr(decision, "metadata", {}) if decision is not None else {}
            ) or new_decision_identity()
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
