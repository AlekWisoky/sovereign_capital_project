from __future__ import annotations

import asyncio
from typing import Any, Dict

from .treasury_governance_truth import treasury_governance_view

_SAFE_TREASURY_OVERLAY_EXCEPTIONS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
)

_SAFE_TREASURY_OVERLAY_LOCAL_EXCEPTIONS = _SAFE_TREASURY_OVERLAY_EXCEPTIONS + (
    KeyError,
    OSError,
)


class RuntimeTreasuryOverlayFacade:
    """Post-decision treasury overlay compatibility facade.

    This isolates additive, deterministic treasury-guided borrow scaling away
    from RuntimeBundle's orchestration loop while preserving the exact
    conditions under which a selected decision may receive a higher
    ``borrow_mult``.
    """

    def _treasury_overlay_guidance(
        self, *, treasury_state: Dict[str, Any] | None
    ) -> Dict[str, float | str | bool]:
        try:
            governance = treasury_governance_view(dict(treasury_state or {}))
            return {
                "cap": float(governance.get("effective_borrow_mult_target_cap") or 1.0),
                "level": str(governance.get("effective_aggressiveness_level") or "LOW").upper(),
                "urgency": float(governance.get("urgency_factor") or 0.0),
                "blocked": bool(governance.get("blocked", False)),
                "reason": str(governance.get("reason") or "ok"),
            }
        except _SAFE_TREASURY_OVERLAY_LOCAL_EXCEPTIONS:
            return {"cap": 1.0, "level": "LOW", "urgency": 0.0, "blocked": False, "reason": "ok"}

    def _apply_treasury_borrow_overlay(
        self,
        *,
        decision: Any,
        treasury_state: Dict[str, Any] | None,
        regime_label: str,
    ) -> Any:
        """Best-effort treasury-guided borrow scaling for a selected decision."""
        try:
            if decision is None or getattr(decision, "action", "skip") != "trade":
                return decision
            guidance = self._treasury_overlay_guidance(treasury_state=treasury_state)
            cap = max(0.50, min(5.0, float(guidance.get("cap", 1.0) or 1.0)))
            cur = float(getattr(decision, "borrow_mult", 1.0) or 1.0)
            p_success = float(getattr(decision, "p_success", 0.0) or 0.0)
            if (
                bool(guidance.get("blocked", False))
                or cap <= cur
                or p_success < 0.85
                or str(regime_label) == "unknown"
            ):
                return decision

            bump = 1.0
            level = str(guidance.get("level", "LOW") or "LOW").upper()
            urgency = float(guidance.get("urgency", 0.0) or 0.0)
            if level == "MODERATE":
                bump = max(cur, 1.10)
            elif level == "HIGH":
                bump = max(cur, 1.25)
            elif level == "MAXIMUM":
                bump = max(cur, 1.40)
            bump *= max(1.0, min(1.25, 1.0 + max(0.0, urgency) * 0.08))
            decision.borrow_mult = float(min(cap, bump))
            return decision
        except _SAFE_TREASURY_OVERLAY_EXCEPTIONS + (asyncio.QueueFull,):
            return decision
