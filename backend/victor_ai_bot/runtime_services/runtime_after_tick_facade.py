from __future__ import annotations

from typing import Any, Dict, List

from ..models import Opportunity


class RuntimeAfterTickFacade:
    """After-tick orchestration compatibility facade.

    This isolates the remaining after-tick residual orchestration from
    ``RuntimeBundle._loop`` while preserving existing auto-dispatch,
    cooldown, engine-tail, post-tick, and loop-tail behavior.
    """

    async def _run_after_tick_orchestration(
        self,
        *,
        current_block: int,
        decision: Any,
        regime_label: str,
        mev_snap: Dict[str, Any] | None,
        opps: List[Opportunity],
        treasury_state: Dict[str, Any] | None,
        tick_failed: bool,
        loop_started_at: float,
    ) -> None:
        # Auto trading: bounded single in-flight task for responsiveness.
        self._maybe_dispatch_auto_trade(current_block=int(current_block), decision=decision)

        # If tripped, stop auto trading until user re-enables.
        if self._auto_trading and not self._cb.allow_auto_trading():
            self._auto_trading = False
            self._errors.append(
                f"circuit_breaker_tripped:cooldown_s={self._cb.remaining_cooldown_s()}"
            )

        # Engine service: normalized engine opportunities across adjacent alpha families.
        if not tick_failed:
            self._scan_engine_opportunities(
                regime_label=str(regime_label or "balanced"),
                mev_state=dict(mev_snap or {}),
                base_opportunities=list(opps or []),
                treasury_state=dict(treasury_state or {}),
            )

        # Phase 7+/V9: same-iteration research/observability tails.
        # Skip them after a contained per-tick bug so they do not
        # consume degraded pre-catch state.
        await self._run_post_tick_tails(tick_failed=bool(tick_failed))

        await self._run_loop_iteration_tail(loop_started_at=float(loop_started_at))
