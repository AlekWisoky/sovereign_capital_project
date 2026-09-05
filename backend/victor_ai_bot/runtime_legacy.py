"""Compatibility shell for runtime bundle construction and entry wrappers.

Heavy runtime behavior lives in focused runtime_services facades and
initialization helpers. This module preserves the public RuntimeBundle /
MultiRuntimeBundle surface and delegates the outer runtime entry points.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List

from .runtime_services.runtime_agent_consensus_facade import RuntimeAgentConsensusFacade
from .runtime_services.runtime_after_tick_facade import RuntimeAfterTickFacade
from .runtime_services.runtime_auto_queue_facade import RuntimeAutoQueueFacade
from .runtime_services.runtime_blockspace_facade import RuntimeBlockspaceFacade
from .runtime_services.runtime_budget_facade import RuntimeBudgetFacade
from .runtime_services.runtime_caq_kds_facade import RuntimeCaqKdsFacade
from .runtime_services.runtime_can_execute_facade import RuntimeCanExecuteFacade
from .runtime_services.runtime_constructor_facade import RuntimeConstructorFacade
from .runtime_services.runtime_decision_facade import RuntimeDecisionFacade
from .runtime_services.runtime_decision_finalize_facade import RuntimeDecisionFinalizeFacade
from .runtime_services.runtime_engine_facade import RuntimeEngineFacade
from .runtime_services.runtime_execute_dispatch_facade import RuntimeExecuteDispatchFacade
from .runtime_services.runtime_execute_entry_facade import RuntimeExecuteEntryFacade
from .runtime_services.runtime_execute_wrapper_facade import RuntimeExecuteWrapperFacade
from .runtime_services.runtime_execution_capture_init import initialize_execution_capture_stack
from .runtime_services.runtime_execution_support_init import initialize_execution_support_stack
from .runtime_services.runtime_feature_bus_facade import RuntimeFeatureBusFacade
from .runtime_services.runtime_institutional_init import initialize_runtime_institutional_stack
from .runtime_services.runtime_lifecycle_facade import RuntimeLifecycleFacade
from .runtime_services.runtime_loop_entry_facade import RuntimeLoopEntryFacade
from .runtime_services.runtime_loop_tail_facade import RuntimeLoopTailFacade
from .runtime_services.runtime_market_facade import RuntimeMarketFacade
from .runtime_services.runtime_multiruntime_lifecycle_facade import RuntimeMultiruntimeLifecycleFacade
from .runtime_services.runtime_multiruntime_meta_facade import RuntimeMultiruntimeMetaFacade
from .runtime_services.runtime_multiruntime_state_facade import RuntimeMultiruntimeStateFacade
from .runtime_services.runtime_optional_family_init import initialize_optional_family_runtimes
from .runtime_services.runtime_optional_overlay_init import initialize_optional_overlay_runtimes
from .runtime_services.runtime_overlay_facade import RuntimeOverlayFacade
from .runtime_services.runtime_operator_facade import RuntimeOperatorFacade
from .runtime_services.runtime_post_tick_facade import RuntimePostTickFacade
from .runtime_services.runtime_postdecision_state_facade import RuntimePostdecisionStateFacade
from .runtime_services.runtime_predecision_state_facade import RuntimePredecisionStateFacade
from .runtime_services.runtime_primary_scan_facade import RuntimePrimaryScanFacade
from .runtime_services.runtime_receipt_facade import RuntimeReceiptFacade
from .runtime_services.runtime_replay_facade import RuntimeReplayFacade
from .runtime_services.runtime_score_overlay_facade import RuntimeScoreOverlayFacade
from .runtime_services.runtime_spread_facade import RuntimeSpreadFacade
from .runtime_services.runtime_state_facade import RuntimeStateFacade
from .runtime_services.runtime_tick_iteration_facade import RuntimeTickIterationFacade
from .runtime_services.runtime_tick_prepare_facade import RuntimeTickPrepareFacade
from .runtime_services.runtime_tick_scan_facade import RuntimeTickScanFacade
from .runtime_services.runtime_treasury_guidance_facade import RuntimeTreasuryGuidanceFacade
from .runtime_services.runtime_treasury_overlay_facade import RuntimeTreasuryOverlayFacade
from .runtime_services.runtime_unit_econ_facade import RuntimeUnitEconFacade

__all__ = ["RuntimeBundle", "MultiRuntimeBundle"]


class MultiRuntimeBundle(
    RuntimeMultiruntimeMetaFacade,
    RuntimeMultiruntimeStateFacade,
    RuntimeMultiruntimeLifecycleFacade,
):
    """Compatibility-shell multiruntime wrapper."""

    @staticmethod
    def dep(request):
        try:
            return request.app.state.runtime  # type: ignore
        except AttributeError:
            return None

    MAX_CHAINS = int(os.environ.get("VICTOR_MULTI_MAX_CHAINS", "4"))
    SNAPSHOT_TIMEOUT_S = float(os.environ.get("VICTOR_MULTI_SNAPSHOT_TIMEOUT_S", "2.0"))
    ALLOW_AUTO_ALL = bool(int(os.environ.get("VICTOR_MULTI_ALLOW_AUTO_ALL", "0")))

    def __init__(self, cfgs: List[Any]):
        if not cfgs:
            raise ValueError("cfgs empty")
        if len(cfgs) > self.MAX_CHAINS:
            cfgs = cfgs[: self.MAX_CHAINS]
        self._runtimes: Dict[str, RuntimeBundle] = {
            c.chain.name: RuntimeBundle(c) for c in cfgs
        }
        self._active_chain = cfgs[0].chain.name
        self._ws_clients: List[asyncio.Queue] = []
        self._fan_tasks: List[asyncio.Task] = []
        self._fan_stop = asyncio.Event()

    @property
    def cfg(self):
        return self._runtimes[self._active_chain].cfg

    def chains(self) -> List[str]:
        return list(self._runtimes.keys())


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
    """Thin compatibility-shell runtime wrapper.

    Constructor sequencing and outer entry wrappers remain here; hot-path
    behavior stays in runtime_services facades.
    """

    @staticmethod
    def dep(request):
        try:
            return request.app.state.runtime  # type: ignore
        except AttributeError:
            return None

    def __init__(self, cfg):
        self._initialize_runtime_constructor_core(cfg)
        data_dir = self.data_dir
        initialize_execution_capture_stack(self, cfg=cfg, data_dir=data_dir)
        initialize_runtime_institutional_stack(self, cfg=cfg, data_dir=data_dir)
        initialize_optional_overlay_runtimes(self, cfg=cfg, data_dir=data_dir)
        initialize_execution_support_stack(self, cfg=cfg, data_dir=data_dir)
        initialize_optional_family_runtimes(self, cfg=cfg, data_dir=data_dir)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.perf_counter()
            await self._run_loop_entry_iteration(loop_started_at=t0)

    async def _execute_auto(self, opp, bn: int, decision: Any = None) -> None:
        """Delegate auto-execution to the canonical dispatch/wrapper facades."""
        prep = await RuntimeExecuteDispatchFacade._prepare_auto_execution_dispatch(
            self, opp=opp, bn=int(bn), decision=decision
        )
        if prep is None:
            return
        await RuntimeExecuteWrapperFacade._run_prepared_auto_execution(
            self,
            opp=prep.opportunity,
            bn=int(bn),
            decision=decision,
            prep=prep,
        )
