from __future__ import annotations

from typing import Any, Dict, List


class RuntimeTickIterationFacade:
    """Own the contained same-tick orchestration for a prepared RPC client.

    This facade intentionally owns the single remaining broad process-boundary
    catch in live backend code. The catch remains narrow in purpose: keep the
    main scan loop alive on an unexpected per-tick bug, record the failure
    deterministically, fail closed for the current tick, and still run the
    after-tick tails against safe defaults.
    """

    async def _run_contained_tick_iteration(
        self,
        *,
        rpc: Any,
        current_block: int,
        loop_started_at: float,
    ) -> None:
        decision = None
        tick_failed = False
        # Safe defaults for the per-tick process-boundary catch below. If an
        # unexpected local bug aborts scan-time preparation, the remainder of the
        # iteration must degrade against defined locals instead of cascading into
        # secondary UnboundLocalError failures.
        opps: List[Any] = []
        regime_label = "balanced"
        treasury_state = None
        mev_snap: Dict[str, Any] = {}

        try:
            tick_state = await self._run_tick_scan_pipeline(
                rpc=rpc,
                current_block=int(current_block),
                loop_started_at=loop_started_at,
            )
            opps = list(tick_state.get("opps") or [])
            regime_label = str(tick_state.get("regime_label") or "balanced")
            treasury_state = dict(tick_state.get("treasury_state") or {})
            mev_snap = dict(tick_state.get("mev_snap") or {})
            decision = tick_state.get("decision")
        except Exception as e:
            # Intentional process-boundary containment: keep the main scan
            # loop alive on an unexpected per-tick bug, while recording the
            # failure deterministically for operator visibility. This is the
            # last remaining broad catch in live backend code and is guarded
            # by test_exception_budget.py. Fail closed for the current tick by
            # clearing any stale opportunity / derived market state before the
            # auto-trading and engine tails run later in the same iteration.
            await self._contain_tick_failure(e)
            tick_failed = True

        await self._run_after_tick_orchestration(
            current_block=int(current_block),
            decision=decision,
            regime_label=str(regime_label or "balanced"),
            mev_snap=dict(mev_snap or {}),
            opps=list(opps or []),
            treasury_state=dict(treasury_state or {}),
            tick_failed=bool(tick_failed),
            loop_started_at=loop_started_at,
        )
