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
    def _safe_mapping(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _attach_capital_demand(self, decision: Any, *, opps: List[Opportunity]) -> Any:
        """Attach a first-class, read-only capital-demand record to the decision.

        ``capital_engine_state()`` is the authority input. This method does not
        authorize capital and does not change execution semantics; it makes the
        requested/authorized capital posture explicit before execution so the
        later execution and settled-outcome records can preserve the same facts.
        """
        if decision is None:
            return decision
        try:
            chosen = next(
                (
                    opp
                    for opp in opps
                    if str(getattr(opp, "id", "")) == str(getattr(decision, "opp_id", ""))
                ),
                None,
            )
            if chosen is None:
                return decision

            capital_reader = getattr(self, "capital_engine_state", None)
            raw_state = capital_reader() if callable(capital_reader) else {}
            root = self._safe_mapping(raw_state)
            engine = self._safe_mapping(root.get("capital_engine")) or root

            def _nonnegative_int(value: Any) -> int:
                try:
                    return max(0, int(value))
                except (TypeError, ValueError, OverflowError):
                    return 0

            legs = getattr(getattr(chosen, "route", None), "legs", []) or []
            base_amount = _nonnegative_int(getattr(legs[0], "amount_in", 0) if legs else 0)
            size_mult = float(getattr(decision, "size_mult", 1.0) or 1.0)
            borrow_mult = float(getattr(decision, "borrow_mult", 1.0) or 1.0)
            requested = max(0, int(base_amount * max(0.0, size_mult) * max(0.0, borrow_mult)))

            available = engine.get("deployable_bankroll_wei")
            if available in (None, ""):
                available = engine.get("allocatable_wei")
            if available in (None, ""):
                available = engine.get("available_wei")
            authorized = _nonnegative_int(available)

            family = str(
                (getattr(chosen, "meta", {}) or {}).get("strategy_family")
                or (getattr(chosen, "meta", {}) or {}).get("route_family")
                or ""
            )
            family_allocations = self._safe_mapping(engine.get("family_allocations_wei"))
            family_authorized = _nonnegative_int(family_allocations.get(family)) if family else 0
            if family_authorized > 0:
                authorized = min(authorized, family_authorized)

            authorized_for_decision = min(requested, authorized) if authorized > 0 else 0
            deployed = 0
            status = (
                "authorized"
                if requested > 0 and authorized_for_decision >= requested
                else (
                    "constrained" if requested > 0 and authorized_for_decision > 0 else "unresolved"
                )
            )

            meta = self._safe_mapping(getattr(chosen, "meta", None))
            goal_posture = (
                meta.get("goal_posture") or meta.get("wealth_goal") or meta.get("goal") or {}
            )
            if not isinstance(goal_posture, dict):
                goal_posture = {"value": goal_posture}

            record = {
                "schema_version": "capital_demand.v1",
                "decision_id": str(getattr(decision, "decision_id", "") or ""),
                "correlation_id": str(getattr(decision, "correlation_id", "") or ""),
                "opportunity_id": str(getattr(chosen, "id", "") or ""),
                "route_id": str(getattr(chosen, "route_id", "") or ""),
                "strategy_family": family,
                "capital_source": str(meta.get("capital_source") or "internal_prime"),
                "requested_capital_wei": str(requested),
                "authorized_capital_wei": str(authorized_for_decision),
                "authority_source": "capital_engine_state",
                "authority_id": str(root.get("authority_id") or engine.get("authority_id") or ""),
                "family_authorized_capital_wei": str(family_authorized),
                "goal_posture": goal_posture,
                "authorization_status": status,
                "ultimately_deployed_capital_wei": str(deployed),
            }
            setattr(decision, "capital_demand", record)
            metadata = getattr(decision, "metadata", None)
            if isinstance(metadata, dict):
                metadata["capital_demand"] = dict(record)
            return decision
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError, RuntimeError):
            return decision

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
        decision = self._attach_capital_demand(decision, opps=opps)

        decision = self._apply_treasury_borrow_overlay(
            decision=decision,
            treasury_state=dict(treasury_state or {}),
            regime_label=str(regime_label),
        )
        identity = identity_from(decision)
        if identity is None or not identity.decision_id or not identity.correlation_id:
            identity = identity_from(getattr(decision, "metadata", {})) or new_decision_identity()
        attach_identity(decision, identity)
        decision = self._attach_capital_demand(decision, opps=opps)

        self._refresh_auto_queue_from_decision(decision, current_block=int(current_block))

        await self._run_postdecision_analytics_state(
            opps=opps,
            rpc=rpc,
            regime_label=str(regime_label or "balanced"),
            current_block=int(current_block),
            loop_started_at=float(loop_started_at),
        )
        return decision
