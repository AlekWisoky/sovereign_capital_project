from __future__ import annotations

import os
from typing import Any, Dict, List

from ..capital_demand import capital_demand_from_mapping
from ..decision_identity import ensure_decision_identity
from ..models import Opportunity
from ..rpc import JsonRpcClient
from ..omar.operator_intent import capture_operator_intent


class RuntimeDecisionFinalizeFacade:
    """Decision-finalization compatibility facade.

    This isolates the remaining decision-finalization chain from
    ``RuntimeBundle._loop`` while preserving existing decision, treasury
    overlay, auto-queue refresh, and post-decision analytics behavior.
    """

    def _ensure_omar_learning_runtime(self) -> Any:
        """Return the production OMAR instance when the explicit gate is on."""
        if (os.environ.get("VICTOR_ENABLE_OMAR", "") or "").strip() != "1":
            return None
        current = getattr(self, "_omar", None)
        if current is not None:
            current.bind_runtime(self)
            return current
        try:
            from ..omar.integration import active_omar_runtime
            from ..omar.runtime import OmarRuntime
            from ..omar.config import OmarConfig

            current = active_omar_runtime()
            if current is None:
                current = OmarRuntime(OmarConfig(enabled=True), chain_name=str(self.cfg.chain.name))
                current.start()
            current.bind_runtime(self)
            self._omar = current
            return current
        except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
            return None

    def _record_omar_decision(
        self, opps: List[Opportunity], decision: Any, current_block: int
    ) -> None:
        if decision is None:
            return
        omar = self._ensure_omar_learning_runtime()
        if omar is None:
            return
        selected = next(
            (
                opp
                for opp in opps
                if str(getattr(opp, "id", "")) == str(getattr(decision, "opp_id", ""))
            ),
            opps[0] if opps else None,
        )
        if selected is None:
            return
        identity = ensure_decision_identity(
            selected,
            decision,
            chain_name=str(getattr(self.cfg.chain, "name", "default")),
            current_block=int(current_block),
        )
        intent = capture_operator_intent(self, decision)
        metadata = getattr(decision, "metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}
            decision.metadata = metadata
        capital_demand = capital_demand_from_mapping(
            {**metadata, **getattr(decision, "__dict__", {})}
        ).to_dict()
        metadata["capital_demand"] = capital_demand
        metadata["operator_intent_snapshot"] = intent.to_dict()
        state = dict(metadata.get("learning_state") or metadata.get("state") or {})
        rl_state = str(getattr(decision, "rl_state", "") or metadata.get("rl_state") or "")
        if rl_state:
            state["rl_state"] = rl_state
        state["capital_demand"] = dict(capital_demand)
        omar.observe_decision(
            decision_id=identity.decision_id,
            correlation_id=identity.correlation_id,
            action=str(getattr(decision, "action", "trade") or "trade"),
            opp_id=str(getattr(selected, "id", "")),
            route_id=str(getattr(selected, "route_id", "")),
            policy_version=str(metadata.get("policy_version") or ""),
            state=state,
            operator_intent=intent,
            metadata={
                "source": "production_runtime_decision_boundary",
                "current_block": int(current_block),
                "capital_demand": dict(capital_demand),
            },
        )

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

        self._record_omar_decision(opps, decision, int(current_block))
        self._refresh_auto_queue_from_decision(decision, current_block=int(current_block))

        await self._run_postdecision_analytics_state(
            opps=opps,
            rpc=rpc,
            regime_label=str(regime_label or "balanced"),
            current_block=int(current_block),
            loop_started_at=float(loop_started_at),
        )
        return decision
