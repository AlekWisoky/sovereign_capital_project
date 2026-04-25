from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ..caq_kds.bus import BUS
from ..models import Opportunity

_SAFE_PREDECISION_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)

_SAFE_PREDECISION_LOCAL_EXCEPTIONS = _SAFE_PREDECISION_EXCEPTIONS + (
    KeyError,
    OSError,
)


class RuntimePredecisionStateFacade:
    """Pre-decision additive state/publication compatibility facade.

    This isolates additive pre-decision state refresh and publication work away
    from RuntimeBundle's orchestration loop while preserving current semantics:
    - unified feature-bus refresh remains additive and best-effort
    - spread scan / publication remains observe-only
    - agent consensus, score overlays, and blockspace observation remain
      pre-decision inputs only
    - typed local failures degrade quietly for the tick
    - unexpected bugs still escape to the process boundary
    """

    def _predecision_bus_snapshot(self) -> Dict[str, Any]:
        try:
            snap = BUS.snapshot()
            return dict(snap) if isinstance(snap, dict) else {}
        except _SAFE_PREDECISION_LOCAL_EXCEPTIONS:
            return {}

    def _run_predecision_additive_state(
        self,
        *,
        opps: List[Opportunity],
        regime_label: str,
        behave_state: Dict[str, Any] | None,
        treasury_state: Dict[str, Any] | None,
        basefee_gwei: float,
        priority_gwei: float,
        mev_risk: float,
        pending_rate: float,
        current_block: int,
    ) -> Dict[str, Any]:
        try:
            self._refresh_unified_feature_bus()
            bus_snap = self._predecision_bus_snapshot()
            mev_snap = (bus_snap.get("mev") if isinstance(bus_snap, dict) else {}) or {}
            mev_state = dict(mev_snap) if isinstance(mev_snap, dict) else {}

            self._run_spread_scan(
                regime_label=str(regime_label),
                mev_risk=float(mev_risk),
                pending_rate=float(pending_rate),
                treasury_state=dict(treasury_state or {}),
            )

            self._run_agent_consensus_gate(
                opps=list(opps or []),
                bus_snap=dict(bus_snap),
                mev_snap=dict(mev_state),
                treasury_state=dict(treasury_state or {}),
                regime_label=str(regime_label),
                current_block=int(current_block),
            )

            self._apply_score_overlays(
                opps=list(opps or []),
                behave_state=behave_state,
                treasury_state=dict(treasury_state or {}),
                regime_label=str(regime_label),
                basefee_gwei=float(basefee_gwei),
                prio_gwei=float(priority_gwei),
                mev_risk=float(mev_risk),
            )

            self._observe_blockspace(
                block_number=int(current_block),
                basefee_gwei=float(basefee_gwei),
                priority_gwei=float(priority_gwei),
                pending_txs=int(len(getattr(self, "_pending", []) or [])),
                mev_risk=float(mev_risk),
            )

            return {
                "bus_snap": dict(bus_snap),
                "mev_snap": dict(mev_state),
            }
        except _SAFE_PREDECISION_EXCEPTIONS:
            return {
                "bus_snap": {},
                "mev_snap": {},
            }
