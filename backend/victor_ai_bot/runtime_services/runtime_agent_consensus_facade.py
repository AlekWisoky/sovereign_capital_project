from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ..caq_kds.bus import BUS
from .treasury_governance_truth import treasury_governance_view
from ..models import Opportunity
from ..portfolio_optimizer import opportunity_route_ready
from .profitability_truth import inspect_profit_after_costs_truth

_SAFE_AGENT_CONSENSUS_EXCEPTIONS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
)

_SAFE_AGENT_LOCAL_EXCEPTIONS = _SAFE_AGENT_CONSENSUS_EXCEPTIONS + (
    KeyError,
    OSError,
)


class RuntimeAgentConsensusFacade:
    """Agent-hub and consensus compatibility facade.

    This isolates additive control-state scoring inputs away from RuntimeBundle's
    orchestration loop while preserving existing side effects on agent/consensus
    state snapshots and bus updates.
    """

    @staticmethod
    def _opp_is_consensus_eligible(opp: Opportunity) -> bool:
        if not bool(getattr(opp, "can_execute", False)):
            return False
        route_ready, _route_reason, _route_reason_codes = opportunity_route_ready(opp)
        if not bool(route_ready):
            return False
        truth = inspect_profit_after_costs_truth(getattr(opp, "meta", None))
        return bool(truth.verified and truth.positive)

    def _agent_hub_local_state(self, opps: List[Opportunity]) -> Dict[str, Any]:
        best = next((o for o in opps if self._opp_is_consensus_eligible(o)), None)
        if best is None:
            return {}
        try:
            meta = best.meta if isinstance(best.meta, dict) else {}
            brain = (meta.get("brain") or {}) if isinstance(meta.get("brain"), dict) else {}
            return {
                "margin_ratio": float(meta.get("margin_ratio", 0.0) or 0.0),
                "gas_ratio": float(meta.get("gas_ratio", 0.0) or 0.0),
                "p_success": float(brain.get("p_success") or meta.get("p_success", 0.0) or 0.0),
                "legs": int(len(getattr(getattr(best, "route", None), "legs", []) or [])),
                "ev_wei": int(brain.get("ev_wei") or 0),
                "id": str(getattr(best, "id", "")),
            }
        except _SAFE_AGENT_LOCAL_EXCEPTIONS:
            return {}

    def _agent_hub_weights(self, *, regime_label: str, hub_out: Any) -> Dict[str, Any]:
        try:
            if getattr(self, "_agent_weighting", None) is None:
                return {}
            return dict(
                self._agent_weighting.weights_for(
                    regime=str(regime_label),
                    agents=list(dict(hub_out.signals).keys()),
                )
                or {}
            )
        except _SAFE_AGENT_LOCAL_EXCEPTIONS:
            return {}

    def _run_agent_consensus_gate(
        self,
        *,
        opps: List[Opportunity],
        bus_snap: Dict[str, Any] | None,
        mev_snap: Dict[str, Any] | None,
        treasury_state: Dict[str, Any] | None,
        regime_label: str,
        current_block: int,
    ) -> Dict[str, Any] | None:
        """Best-effort agent-hub and consensus scoring gate for the current tick."""
        try:
            local = self._agent_hub_local_state(list(opps or []))
            hub_out = None
            if getattr(self, "_agent_hub", None) is not None:
                treasury_governance = treasury_governance_view(dict(treasury_state or {}))
                hub_out = self._agent_hub.step(
                    state={
                        "local": dict(local),
                        "mev": dict(mev_snap or {}),
                        "dex": dict(
                            (bus_snap.get("dex") or {}) if isinstance(bus_snap, dict) else {}
                        ),
                        "cex": dict(
                            (bus_snap.get("cex") or {}) if isinstance(bus_snap, dict) else {}
                        ),
                        "treasury": {
                            "borrow_mult_target_cap": float(
                                treasury_governance.get("effective_borrow_mult_target_cap") or 1.0
                            ),
                            "aggressiveness_level": str(
                                treasury_governance.get("effective_aggressiveness_level") or "LOW"
                            ),
                            "urgency_factor": float(
                                treasury_governance.get("urgency_factor") or 0.0
                            ),
                            "governance_blocked": bool(treasury_governance.get("blocked", False)),
                            "governance_reason": str(treasury_governance.get("reason") or "ok"),
                        },
                    }
                )
                weights = self._agent_hub_weights(regime_label=str(regime_label), hub_out=hub_out)
                self._agent_hub_last = {
                    "signals": dict(hub_out.signals),
                    "confidences": dict(hub_out.confidences),
                    "outputs": dict(hub_out.outputs),
                    "contracts": dict((hub_out.contracts or {})),
                    "health": dict((getattr(hub_out, "health", None) or {})),
                    "mandates": dict((getattr(hub_out, "mandates", None) or {})),
                    "weights": dict(weights),
                    "regime": str(regime_label),
                    "portfolio_manager": dict((getattr(hub_out, "portfolio_manager", None) or {})),
                }
            cons = None
            if getattr(self, "_consensus", None) is not None:
                cons = self._consensus.compute(
                    signals=(hub_out.signals if hub_out is not None else {}),
                    confidences=(hub_out.confidences if hub_out is not None else {}),
                    regime=str(regime_label),
                    strategy_type="dex_flash",
                    deterministic_key=f"{int(current_block)}:{str(local.get('id', ''))}",
                )
                self._consensus_last = dict(cons)
                BUS.update("consensus", dict(cons))
            return {
                "local": dict(local),
                "agent_hub_last": dict(getattr(self, "_agent_hub_last", {}) or {}),
                "consensus_last": dict(getattr(self, "_consensus_last", {}) or {}),
                "consensus": (dict(cons) if cons is not None else None),
            }
        except _SAFE_AGENT_CONSENSUS_EXCEPTIONS + (asyncio.QueueFull,):
            return None
