from __future__ import annotations

from typing import Any, Dict, List

from ..decision_identity import ensure_decision_identity
from ..identity import attach_identity, identity_from, new_decision_identity
from ..models import Opportunity
from ..omar.operator_intent import capture_operator_intent, operator_intent_fingerprint
from ..rpc import JsonRpcClient


class RuntimeDecisionFinalizeFacade:
    """Decision-finalization compatibility facade.

    This isolates the remaining decision-finalization chain from
    ``RuntimeBundle._loop`` while preserving existing decision, treasury
    overlay, auto-queue refresh, and post-decision analytics behavior.
    """

    def _ensure_decision_identity(
        self,
        decision: Any,
        *,
        opps: List[Opportunity],
        operator_intent: Any = None,
        intent_fingerprint: str = "",
        current_block: int = 0,
    ) -> Any:
        """Make lifecycle identity and decision-time intent explicit."""
        if decision is None:
            return decision
        opportunity = opps[0] if opps else decision
        identity = ensure_decision_identity(
            opportunity,
            decision,
            chain_name=str(getattr(getattr(self, "cfg", None), "chain", None).name)
            if getattr(getattr(self, "cfg", None), "chain", None) is not None
            else "default",
            current_block=int(current_block),
            operator_intent=operator_intent,
            intent_fingerprint=intent_fingerprint,
        )
        try:
            metadata = getattr(decision, "metadata", None)
            if isinstance(metadata, dict):
                metadata.setdefault("decision_context", {}).update(
                    {"candidate_count": int(len(opps or []))}
                )
        except (AttributeError, TypeError, ValueError):
            pass
        attach_identity(decision, identity)
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

        # Freeze the effective operator context before identity finalization so
        # historical learning can attribute the exact human/goal/AI posture that
        # produced this decision. The snapshot is context only; governance,
        # capital authority, and execution remain authoritative.
        operator_intent = capture_operator_intent(self, decision)
        intent_fingerprint = operator_intent_fingerprint(operator_intent)
        decision = self._ensure_decision_identity(
            decision,
            opps=opps,
            operator_intent=operator_intent,
            intent_fingerprint=intent_fingerprint,
            current_block=int(current_block),
        )

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

        # Preserve the immutable decision-time intent/fingerprint across any
        # replacement object returned by treasury guidance.
        try:
            metadata = getattr(decision, "metadata", None)
            if isinstance(metadata, dict):
                metadata.setdefault("operator_intent_snapshot", operator_intent.to_dict())
                metadata.setdefault("intent_fingerprint", intent_fingerprint)
                lineage = metadata.setdefault("canonical_lineage", {})
                lineage.setdefault("operator_intent", operator_intent.to_dict())
                lineage.setdefault("intent_fingerprint", intent_fingerprint)
        except (AttributeError, TypeError, ValueError):
            pass

        self._refresh_auto_queue_from_decision(decision, current_block=int(current_block))

        await self._run_postdecision_analytics_state(
            opps=opps,
            rpc=rpc,
            regime_label=str(regime_label or "balanced"),
            current_block=int(current_block),
            loop_started_at=float(loop_started_at),
        )
        return decision
