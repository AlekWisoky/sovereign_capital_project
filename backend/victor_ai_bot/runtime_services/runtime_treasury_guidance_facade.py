from __future__ import annotations

from typing import Any, Dict, List

from ..caq_kds.bus import BUS
from ..models import Opportunity

_SAFE_TREASURY_GUIDANCE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeTreasuryGuidanceFacade:
    """Pre-decision treasury guidance compatibility facade.

    This isolates treasury pre-selection, treasury bus publication, and the
    optional BehaveAgent treasury-guided overlay away from RuntimeBundle's
    orchestration loop while preserving the existing best-effort semantics.
    """

    def _treasury_bankroll_state(self) -> Dict[str, int]:
        state = getattr(self._bankroll, "state")
        return {
            "realized_profit_wei": int(getattr(state, "realized_profit_wei", 0) or 0),
            "last_amount_in_wei": int(getattr(state, "last_amount_in_wei", 0) or 0),
            "success_streak": int(getattr(state, "success_streak", 0) or 0),
            "fail_streak": int(getattr(state, "fail_streak", 0) or 0),
            "updated_ts_ms": int(getattr(state, "updated_ts_ms", 0) or 0),
            "profit_updated_ts_ms": int(getattr(state, "profit_updated_ts_ms", 0) or 0),
            "sizing_updated_ts_ms": int(getattr(state, "sizing_updated_ts_ms", 0) or 0),
        }

    def _apply_treasury_guidance(
        self,
        *,
        behave_state: Dict[str, Any] | None,
        regime_label: str,
        opps: List[Opportunity],
        current_block: int,
    ) -> Dict[str, Any]:
        """Best-effort treasury pre-select and Behave overlay application."""
        treasury = getattr(self, "_treasury", None)
        if treasury is None:
            return {"treasury_state": None, "behave_state": behave_state}
        try:
            treasury_state = treasury.pre_select_strategy(
                bankroll_state=self._treasury_bankroll_state(),
                volatility_regime=str(regime_label),
            )
            BUS.update("treasury", dict(treasury_state or {}))
            behave_state = self._behave_strategy_overlay(
                behave_state=behave_state,
                treasury_state=dict(treasury_state or {}),
                opps=list(opps or []),
                current_block=int(current_block),
            )
            return {"treasury_state": treasury_state, "behave_state": behave_state}
        except _SAFE_TREASURY_GUIDANCE_EXCEPTIONS:
            return {"treasury_state": None, "behave_state": behave_state}
