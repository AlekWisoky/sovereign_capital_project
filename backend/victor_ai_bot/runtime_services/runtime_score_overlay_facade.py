from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ..models import Opportunity

_SAFE_SCORE_OVERLAY_EXCEPTIONS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
)

_SAFE_SCORE_OVERLAY_LOCAL_EXCEPTIONS = _SAFE_SCORE_OVERLAY_EXCEPTIONS + (
    KeyError,
    OSError,
)


class RuntimeScoreOverlayFacade:
    """Per-opportunity score-overlay compatibility facade.

    This isolates additive, deterministic scoring-input annotations away from
    RuntimeBundle's orchestration loop while preserving the exact overlay
    payload written into each opportunity's ``meta['overlay']`` map.
    """

    def _score_overlay_priorities(self, *, behave_state: Dict[str, Any] | None) -> Dict[str, Any]:
        try:
            pri = (behave_state or {}).get("strategy_priority_matrix") or {}
            return dict(pri) if isinstance(pri, dict) else {}
        except _SAFE_SCORE_OVERLAY_LOCAL_EXCEPTIONS:
            return {}

    def _score_overlay_consensus(self) -> Dict[str, Any]:
        try:
            snap = getattr(self, "_consensus_last", {}) or {}
            return dict(snap) if isinstance(snap, dict) else {}
        except _SAFE_SCORE_OVERLAY_LOCAL_EXCEPTIONS:
            return {}

    def _apply_score_overlays(
        self,
        *,
        opps: List[Opportunity],
        behave_state: Dict[str, Any] | None,
        treasury_state: Dict[str, Any] | None,
        regime_label: str,
        basefee_gwei: float,
        prio_gwei: float,
        mev_risk: float,
    ) -> None:
        """Best-effort per-opportunity score-overlay annotation for the current tick."""
        try:
            pri = self._score_overlay_priorities(behave_state=behave_state)
            consensus = self._score_overlay_consensus()
            baseline = 1.0 / 9.0  # matches default number of strategy types in workflow.py
            ag_mult = float(
                (
                    (
                        ((treasury_state or {}).get("aggressiveness") or {}).get(
                            "aggressiveness_multiplier"
                        )
                    )
                    or 1.0
                )
            )
            ag_mult = max(0.80, min(1.50, ag_mult))
            for opp in opps:
                try:
                    legs = int(len(getattr(getattr(opp, "route", None), "legs", []) or []))
                    stype = "dex_flash_3leg" if legs >= 3 else "dex_flash_2leg"
                    w = float(pri.get(stype, baseline) or baseline)
                    w = max(0.0, min(1.0, w))
                    bias = 1.0 + (w - baseline) * 1.2
                    bias = max(0.70, min(1.30, bias))
                    bias = max(0.60, min(1.50, bias * ag_mult))
                    if not isinstance(opp.meta, dict):
                        opp.meta = {}
                    opp.meta.setdefault("overlay", {})
                    opp.meta["overlay"].update(
                        {
                            "score_multiplier": float(bias),
                            "regime_label": str(regime_label),
                            "basefee_gwei": float(basefee_gwei),
                            "priority_gwei": float(prio_gwei),
                            "mev_risk": float(mev_risk),
                            "consensus_score": float(consensus.get("consensus_score", 0.0) or 0.0),
                            "consensus_allow": bool(consensus.get("allow", False)),
                        }
                    )
                except _SAFE_SCORE_OVERLAY_LOCAL_EXCEPTIONS:
                    continue
        except _SAFE_SCORE_OVERLAY_EXCEPTIONS + (asyncio.QueueFull,):
            return
