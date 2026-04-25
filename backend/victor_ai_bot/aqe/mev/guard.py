from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .models import MEVConfig

_SAFE_GUARD_EXCEPTIONS = (AttributeError, TypeError, ValueError)


@dataclass
class MEVGuardDecision:
    allow: bool
    risk: float
    reason: str
    suggested_send_mode: str = ""
    meta: Dict[str, Any] | None = None


class MEVGuard:
    """Execution-time guardrail that can block unsafe public submissions.

    This uses MEVRuntime's best-effort mempool statistics. It is intentionally
    conservative and designed to reduce accidental leakage of profitable routes.
    """

    def __init__(self, *, cfg: MEVConfig, mev_runtime: Any):
        self.cfg = cfg
        self._mev = mev_runtime

    def assess(self, *, opp: Any, send_mode: str) -> MEVGuardDecision:
        # If not enabled, always allow.
        if not self.cfg.enabled:
            return MEVGuardDecision(True, 0.0, "disabled", meta={})

        st: Dict[str, Any] = {}
        try:
            st = self._mev.state() if self._mev is not None else {}
        except _SAFE_GUARD_EXCEPTIONS:
            st = {}

        # Core signal: p90 risk proxy + high-risk ratio.
        p90 = float(st.get("sandwich_risk_p90") or 0.0)
        high = float(st.get("high_risk_ratio") or 0.0)
        base_risk = max(p90, min(1.0, high * 1.2))

        # Route heuristic: if route hits common swap venues, bump risk slightly.
        bump = 0.0
        try:
            legs = list(getattr(getattr(opp, "route", None), "legs", []) or [])
            for lg in legs:
                dex = str(getattr(lg, "dex", "") or "").lower()
                if "uni" in dex or "v3" in dex or "curve" in dex or "balancer" in dex:
                    bump = max(bump, 0.10)
        except _SAFE_GUARD_EXCEPTIONS:
            pass

        risk = max(0.0, min(1.0, base_risk + bump))

        meta = {
            "p90": p90,
            "high_ratio": high,
            "bump": bump,
            "connected": bool(st.get("connected")) if isinstance(st, dict) else False,
        }

        # Safety rail: block public submission when high risk.
        if self.cfg.refuse_public_send_on_high_risk and str(send_mode) == "public" and risk >= float(self.cfg.high_risk_threshold):
            sug = "private" if self.cfg.suggest_private_when_risky else ""
            return MEVGuardDecision(False, risk, "mev_guard_block_public_high_risk", suggested_send_mode=sug, meta=meta)

        # Otherwise allow, maybe suggest private.
        sug = ""
        if self.cfg.suggest_private_when_risky and risk >= float(self.cfg.high_risk_threshold):
            sug = "private"
        return MEVGuardDecision(True, risk, "ok", suggested_send_mode=sug, meta=meta)
