"""Compatibility shell for runtime bundle construction and entry wrappers.

This module intentionally stays thin.
Heavy runtime behavior now lives in focused runtime_services facades and
initialization helpers. The remaining responsibilities here are:
- preserving the public RuntimeBundle / MultiRuntimeBundle import surface
- sequencing constructor helper wiring
- delegating the outer loop and auto-execution entry wrappers

The single broad process-boundary containment site lives outside this module in
runtime_tick_iteration_facade, where it can be regression-tested explicitly.
"""

from __future__ import annotations
import asyncio, time, os
from typing import List, Optional, Dict, Any
from .rpc import JsonRpcClient
from .deploy_mode import is_public_mode, public_broadcast_override_enabled
from .arb_engine import requote_opportunity
from .execution import try_execute_opportunity
from .jsonsafe import to_json_safe
from .income import classify_opportunity_income
from .models import Opportunity, RuntimeState
from .caq_kds.bus import BUS
from .execution_capture.smart_order_router import (
    VenueScorecardStore,
    size_bucket_for,
    latency_class_for,
)
from .execution_capture.envelope import build_opportunity_envelope
from .telemetry.fund_summary import build_fund_health_summary
from .treasury.journal import record_borrow_cost, record_realized_pnl
from .treasury.reconciliation import reconcile_balances
from .internal_prime.contracts import PrimeBorrowRequest
from .runtime_services.runtime_state_facade import RuntimeStateFacade
from .runtime_services.runtime_constructor_facade import RuntimeConstructorFacade
from .runtime_services.runtime_overlay_facade import RuntimeOverlayFacade
from .runtime_services.runtime_operator_facade import RuntimeOperatorFacade
from .runtime_services.runtime_replay_facade import RuntimeReplayFacade
from .runtime_services.runtime_capital_facade import RuntimeCapitalFacade
from .runtime_services.runtime_receipt_facade import RuntimeReceiptFacade
from .runtime_services.runtime_lifecycle_facade import RuntimeLifecycleFacade
from .runtime_services.runtime_market_facade import RuntimeMarketFacade
from .runtime_services.runtime_budget_facade import RuntimeBudgetFacade
from .runtime_services.runtime_treasury_guidance_facade import RuntimeTreasuryGuidanceFacade
from .runtime_services.runtime_primary_scan_facade import RuntimePrimaryScanFacade
from .runtime_services.runtime_execute_dispatch_facade import RuntimeExecuteDispatchFacade
from .runtime_services.runtime_execute_wrapper_facade import RuntimeExecuteWrapperFacade
from .runtime_services.runtime_execute_entry_facade import RuntimeExecuteEntryFacade
from .runtime_services.runtime_predecision_state_facade import RuntimePredecisionStateFacade
from .runtime_services.runtime_decision_finalize_facade import RuntimeDecisionFinalizeFacade
from .runtime_services.runtime_tick_scan_facade import RuntimeTickScanFacade
from .runtime_services.runtime_tick_prepare_facade import RuntimeTickPrepareFacade
from .runtime_services.runtime_tick_iteration_facade import RuntimeTickIterationFacade
from .runtime_services.runtime_loop_entry_facade import RuntimeLoopEntryFacade
from .runtime_services.runtime_decision_facade import RuntimeDecisionFacade
from .runtime_services.runtime_auto_queue_facade import RuntimeAutoQueueFacade
from .runtime_services.runtime_engine_facade import RuntimeEngineFacade
from .runtime_services.runtime_post_tick_facade import RuntimePostTickFacade
from .runtime_services.runtime_loop_tail_facade import RuntimeLoopTailFacade
from .runtime_services.runtime_after_tick_facade import RuntimeAfterTickFacade
from .runtime_services.runtime_unit_econ_facade import RuntimeUnitEconFacade
from .runtime_services.runtime_postdecision_state_facade import RuntimePostdecisionStateFacade
from .runtime_services.runtime_caq_kds_facade import RuntimeCaqKdsFacade
from .runtime_services.runtime_feature_bus_facade import RuntimeFeatureBusFacade
from .runtime_services.runtime_spread_facade import RuntimeSpreadFacade
from .runtime_services.runtime_blockspace_facade import RuntimeBlockspaceFacade
from .runtime_services.runtime_agent_consensus_facade import RuntimeAgentConsensusFacade
from .runtime_services.runtime_score_overlay_facade import RuntimeScoreOverlayFacade
from .runtime_services.runtime_treasury_overlay_facade import RuntimeTreasuryOverlayFacade
from .runtime_services.runtime_can_execute_facade import RuntimeCanExecuteFacade
from .runtime_services.runtime_multiruntime_meta_facade import RuntimeMultiruntimeMetaFacade
from .runtime_services.runtime_multiruntime_state_facade import RuntimeMultiruntimeStateFacade
from .runtime_services.runtime_multiruntime_lifecycle_facade import (
    RuntimeMultiruntimeLifecycleFacade,
)
from .runtime_services.runtime_optional_family_init import initialize_optional_family_runtimes
from .runtime_services.runtime_optional_overlay_init import initialize_optional_overlay_runtimes
from .runtime_services.runtime_execution_capture_init import initialize_execution_capture_stack
from .runtime_services.runtime_execution_support_init import initialize_execution_support_stack
from .runtime_services.runtime_institutional_init import initialize_runtime_institutional_stack

__all__ = ["RuntimeBundle", "MultiRuntimeBundle"]

# Stable compatibility seam for legacy/runtime harnesses and execution wrapper
# tests. The canonical execution wrapper now lives in
# runtime_execute_wrapper_facade, but patching this module remains supported so
# external harnesses do not need to reach into deeper runtime internals.

_SAFE_RUNTIME_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class MultiRuntimeBundle(
    RuntimeMultiruntimeMetaFacade,
    RuntimeMultiruntimeStateFacade,
    RuntimeMultiruntimeLifecycleFacade,
):
    """Compatibility-shell multiruntime wrapper.

    Run multiple RuntimeBundle instances safely.

    This is an additive feature to support targeting **both mainnet and L2s**.
    - Existing /api/state and /ws continue to reflect the *active* chain.
    - New /api/multichain/* endpoints expose the aggregated state.

    Safety defaults:
    - Hard cap number of chains to avoid runaway resource usage.
    - Per-snapshot timeouts to keep API responsive even if one chain stalls.
    """

    @staticmethod
    def dep(request):
        """FastAPI dependency helper for multi-chain runtime."""
        try:
            return request.app.state.runtime  # type: ignore
        except AttributeError:
            return None

    MAX_CHAINS = int(os.environ.get("VICTOR_MULTI_MAX_CHAINS", "4"))
    SNAPSHOT_TIMEOUT_S = float(os.environ.get("VICTOR_MULTI_SNAPSHOT_TIMEOUT_S", "2.0"))
    # Safety default: do NOT auto-trade on multiple chains unless explicitly enabled.
    # 0 = only active chain may auto-trade, others forced off.
    # 1 = allow each chain's configured auto_trading to run concurrently (higher risk).
    ALLOW_AUTO_ALL = bool(int(os.environ.get("VICTOR_MULTI_ALLOW_AUTO_ALL", "0")))

    def __init__(self, cfgs: List[Any]):
        if not cfgs:
            raise ValueError("cfgs empty")
        if len(cfgs) > self.MAX_CHAINS:
            cfgs = cfgs[: self.MAX_CHAINS]

        self._runtimes: Dict[str, RuntimeBundle] = {c.chain.name: RuntimeBundle(c) for c in cfgs}
        # active is the first config
        self._active_chain: str = cfgs[0].chain.name

        # websocket fan-in
        self._ws_clients: List[asyncio.Queue] = []
        self._fan_tasks: List[asyncio.Task] = []
        self._fan_stop = asyncio.Event()

    @property
    def cfg(self):
        return self._runtimes[self._active_chain].cfg

    def chains(self) -> List[str]:
        return list(self._runtimes.keys())

    # --- API surface matching RuntimeBundle ---


class RuntimeBundle(
    RuntimeOverlayFacade,
    RuntimeOperatorFacade,
    RuntimeReplayFacade,
    RuntimeCapitalFacade,
    RuntimeReceiptFacade,
    RuntimeLifecycleFacade,
    RuntimeMarketFacade,
    RuntimeBudgetFacade,
    RuntimeTreasuryGuidanceFacade,
    RuntimePrimaryScanFacade,
    RuntimeExecuteDispatchFacade,
    RuntimeExecuteWrapperFacade,
    RuntimeExecuteEntryFacade,
    RuntimePredecisionStateFacade,
    RuntimeDecisionFinalizeFacade,
    RuntimeTickScanFacade,
    RuntimeTickPrepareFacade,
    RuntimeTickIterationFacade,
    RuntimeLoopEntryFacade,
    RuntimeDecisionFacade,
    RuntimeAutoQueueFacade,
    RuntimeEngineFacade,
    RuntimePostTickFacade,
    RuntimeLoopTailFacade,
    RuntimeAfterTickFacade,
    RuntimeUnitEconFacade,
    RuntimePostdecisionStateFacade,
    RuntimeCaqKdsFacade,
    RuntimeFeatureBusFacade,
    RuntimeSpreadFacade,
    RuntimeBlockspaceFacade,
    RuntimeAgentConsensusFacade,
    RuntimeScoreOverlayFacade,
    RuntimeTreasuryOverlayFacade,
    RuntimeCanExecuteFacade,
    RuntimeConstructorFacade,
    RuntimeStateFacade,
):
    """Compatibility-shell runtime wrapper.

    This class deliberately keeps only constructor sequencing and the two outer
    runtime entry wrappers. Hot-path behavior lives in runtime_services facades.
    """

    @staticmethod
    def dep(request):
        """FastAPI dependency helper.

        Some API routes use Depends(RuntimeBundle.dep) to access the runtime.
        This is intentionally lightweight and keeps backward compatibility.
        """
        try:
            return request.app.state.runtime  # type: ignore
        except AttributeError:
            return None

    def __init__(self, cfg):
        self._initialize_runtime_constructor_core(cfg)
        data_dir = self.data_dir

        initialize_execution_capture_stack(self, cfg=cfg, data_dir=data_dir)
        initialize_runtime_institutional_stack(self, cfg=cfg, data_dir=data_dir)

        # Phase 14+/20+/21+: optional control overlays (additive, optional).
        initialize_optional_overlay_runtimes(self, cfg=cfg, data_dir=data_dir)

        initialize_execution_support_stack(self, cfg=cfg, data_dir=data_dir)
        initialize_optional_family_runtimes(self, cfg=cfg, data_dir=data_dir)

    # --- Phase B8: addit...

    async def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.perf_counter()
            await self._run_loop_entry_iteration(loop_started_at=t0)

    async def _execute_auto(self, opp: Opportunity, bn: int, decision: Any = None) -> None:
        """Compatibility wrapper delegating to the canonical entry facade.

        Real RuntimeBundle instances use `_execute_auto_entry` from
        RuntimeExecuteEntryFacade. Lightweight legacy harnesses may provide
        only the lower-level facade methods, so the historical unbound-call
        behavior remains available as a fallback.
        """
        entry = getattr(self, "_execute_auto_entry", None)
        if callable(entry):
            await entry(opp=opp, bn=int(bn), decision=decision)
            return

        prep_fn = getattr(self, "_prepare_auto_execution_dispatch", None)
        uses_facade_prep = not callable(prep_fn)
        if uses_facade_prep:
            prep_fn = RuntimeExecuteDispatchFacade._prepare_auto_execution_dispatch
        if uses_facade_prep:
            prep = await prep_fn(self, opp=opp, bn=int(bn), decision=decision)
        else:
            prep = await prep_fn(opp=opp, bn=int(bn), decision=decision)
        if prep is None:
            return

        wrapper_fn = getattr(self, "_run_prepared_auto_execution", None)
        uses_facade_wrapper = not callable(wrapper_fn)
        if uses_facade_wrapper:
            wrapper_fn = RuntimeExecuteWrapperFacade._run_prepared_auto_execution
            legacy_identity = getattr(self, "_ensure_execution_identity", None)
            if not callable(legacy_identity):
                setattr(self, "_ensure_execution_identity", lambda result, _decision: result)
        try:
            if uses_facade_wrapper:
                await wrapper_fn(
                    self,
                    opp=prep.opportunity,
                    bn=int(bn),
                    decision=decision,
                    prep=prep,
                )
            else:
                await wrapper_fn(
                    opp=prep.opportunity,
                    bn=int(bn),
                    decision=decision,
                    prep=prep,
                )
        finally:
            if uses_facade_wrapper and not callable(legacy_identity):
                try:
                    delattr(self, "_ensure_execution_identity")
                except AttributeError:
                    pass
