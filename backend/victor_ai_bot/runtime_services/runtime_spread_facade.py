from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

from ..caq_kds.bus import BUS
from .treasury_governance_truth import treasury_governance_view

_SAFE_SPREAD_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeSpreadFacade:
    """Spread-engine scan/publication compatibility facade.

    This isolates additive multi-venue spread scanning and publication away
    from RuntimeBundle's orchestration loop while preserving the current
    observe-only semantics:
    - spread scanning remains additive and non-submission
    - spread state shaping remains deterministic
    - typed local failures degrade quietly for the tick
    - unexpected bugs still escape to the process boundary
    """

    def _spread_quotes(self) -> List[Dict[str, Any]]:
        try:
            if getattr(self, "_arbitrage", None) is None:
                return []
            state = self._arbitrage.state()
            if not isinstance(state, dict):
                return []
            quotes = state.get("quotes") or []
            return list(quotes) if isinstance(quotes, list) else []
        except _SAFE_SPREAD_EXCEPTIONS:
            return []

    def _spread_scan_state(
        self,
        *,
        regime_label: str,
        mev_risk: float,
        pending_rate: float,
        treasury_state: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        governance = treasury_governance_view(dict(treasury_state or {}))
        aggressiveness_level = str(governance.get("effective_aggressiveness_level") or "LOW")
        return {
            "quotes": self._spread_quotes(),
            "regime": str(regime_label),
            "stress": {"mev": float(mev_risk), "pending_rate": float(pending_rate)},
            "aggressiveness_level": aggressiveness_level,
        }

    def _run_spread_scan(
        self,
        *,
        regime_label: str,
        mev_risk: float,
        pending_rate: float,
        treasury_state: Dict[str, Any] | None,
    ) -> bool:
        try:
            spread_state = self._spread_scan_state(
                regime_label=str(regime_label),
                mev_risk=float(mev_risk),
                pending_rate=float(pending_rate),
                treasury_state=dict(treasury_state or {}),
            )
            opps_spread = []
            if getattr(self, "_spread_engine", None) is not None:
                opps_spread = self._spread_engine.scan(spread_state)
            self._spread_opps = list(opps_spread)
            self._spread_last = {
                "ts": int(time.time()),
                "regime": str(regime_label),
                "count": int(len(opps_spread)),
            }
            BUS.update(
                "spread",
                {
                    "count": int(len(opps_spread)),
                    "top": (opps_spread[0].as_dict() if opps_spread else None),
                },
            )
            return True
        except _SAFE_SPREAD_EXCEPTIONS:
            return False
