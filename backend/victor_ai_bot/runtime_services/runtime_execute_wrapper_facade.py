from __future__ import annotations

import importlib
import time
from typing import Any, Awaitable, Callable, Tuple

from ..decision_identity import attach_execution_identity, create_execution_identity
from ..execution import try_execute_opportunity
from ..execution_capture.b4_execution_binding import (
    ExecutionQuoteBindingError,
    bind_final_quote_to_execution,
)
from ..latency_profiler import LatencySpan
from ..rpc import JsonRpcClient
from .execution_service import ExecutionService
from .runtime_execute_dispatch_facade import AutoExecutionDispatchContext


_DefaultTryExecute = Callable[..., Awaitable[Any]]
_DefaultRpcClient = type[JsonRpcClient]
_DEFAULT_JSON_RPC_CLIENT = JsonRpcClient
_DEFAULT_TRY_EXECUTE = try_execute_opportunity


def _compat_execution_wrapper_symbols() -> Tuple[_DefaultRpcClient, _DefaultTryExecute]:
    """Return the canonical execution-wrapper patch seam."""

    rpc_cls = JsonRpcClient
    execute_fn = try_execute_opportunity
    try:
        runtime_legacy = importlib.import_module("victor_ai_bot.runtime_legacy")
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
        return rpc_cls, execute_fn

    legacy_rpc = getattr(runtime_legacy, "JsonRpcClient", _DEFAULT_JSON_RPC_CLIENT)
    legacy_exec = getattr(runtime_legacy, "try_execute_opportunity", _DEFAULT_TRY_EXECUTE)
    if legacy_rpc is not _DEFAULT_JSON_RPC_CLIENT:
        rpc_cls = legacy_rpc
    if legacy_exec is not _DEFAULT_TRY_EXECUTE:
        execute_fn = legacy_exec
    return rpc_cls, execute_fn


class RuntimeExecuteWrapperFacade:
    """Compatibility facade for prepared auto-execution wrapper flow."""

    async def _run_prepared_auto_execution(
        self,
        *,
        opp: Any,
        bn: int,
        decision: Any,
        prep: AutoExecutionDispatchContext,
    ) -> None:
        force_dry = bool(prep.force_dry)
        old_gas_mode = str(prep.old_gas_mode)
        old_send_mode = str(prep.old_send_mode)
        read_url = str(prep.read_url)
        send_url = str(prep.send_url)

        try:
            rpc_client_cls, execute_opportunity = _compat_execution_wrapper_symbols()
            async with (
                rpc_client_cls(read_url, timeout_s=10.0, max_concurrency=20, max_batch=50) as rpc_r,
                rpc_client_cls(send_url, timeout_s=10.0, max_concurrency=10, max_batch=20) as rpc_s,
            ):
                # The execution boundary is the first point at which a concrete
                # attempt exists. This identity is distinct from decision_id and
                # remains stable across the execution/receipt/settlement chain.
                execution_identity = create_execution_identity(decision, opp)
                attach_execution_identity(
                    execution_identity,
                    decision=decision,
                    opp=opp,
                )

                t1 = time.perf_counter()
                span = LatencySpan()
                sizing_binding_applied = False
                original_size_mult = getattr(decision, "size_mult", None)
                original_borrow_mult = getattr(decision, "borrow_mult", None)
                had_size_mult = hasattr(decision, "size_mult")
                had_borrow_mult = hasattr(decision, "borrow_mult")

                try:
                    # B4.2: once canonical institutional sizing exists, bind that
                    # exact USD notional to the authoritative execution-time quote
                    # and requote the route at the resulting raw amount. The
                    # existing execution.py then consumes opp.route.legs[0].amount_in
                    # when constructing amountBorrow. This does not mint a second
                    # sizing identity.
                    try:
                        binding = await bind_final_quote_to_execution(
                            rpc_read=rpc_r,
                            cfg=self.cfg,
                            cache=self.cache,
                            opp=opp,
                            decision=decision,
                            block_number=int(bn),
                        )
                    except ExecutionQuoteBindingError as exc:
                        binding = None
                        if str(exc) not in {
                            "sizing_id_required",
                            "approved_notional_usd_missing",
                        }:
                            raise

                    if binding is not None:
                        sizing_binding_applied = True
                        # execution.py historically applies decision size_mult /
                        # borrow_mult itself. Those modifiers are already embodied
                        # by the canonical sizing decision, so suppress only the
                        # duplicate execution-layer multiplier for this invocation.
                        try:
                            decision.size_mult = 1.0
                            decision.borrow_mult = 1.0
                        except (AttributeError, TypeError):
                            raise ExecutionQuoteBindingError("decision_action_override_unavailable")

                    async def _core():
                        return await execute_opportunity(
                            rpc_r,
                            rpc_s,
                            self.cfg,
                            opp,
                            bn,
                            self._last_submitted_block,
                            cache=self.cache,
                            decision=decision,
                            force_dry_run=force_dry,
                            mev_guard=getattr(self, "_mev_guard", None),
                            profiler=span,
                        )

                    execution_service = getattr(self, "_execution_service", None)
                    if execution_service is not None:
                        fioa_handler = getattr(execution_service, "handle_fioa_execution_wrapper", None)
                        if callable(fioa_handler):
                            res = await fioa_handler(self, opp, decision, _core)
                        else:
                            res = await ExecutionService.handle_fioa_execution_wrapper(
                                execution_service,
                                self,
                                opp,
                                decision,
                                _core,
                            )
                    else:
                        res = await _core()

                    # The physical execution adapter may add tx_hash/receipt facts;
                    # preserve the same execution identity beside those facts.
                    attach_execution_identity(
                        execution_identity,
                        decision=decision,
                        opp=opp,
                        result=res,
                    )

                    if sizing_binding_applied and isinstance(getattr(res, "plan", None), dict):
                        res.plan["b4_execution_quote"] = dict(
                            getattr(opp, "meta", {}).get("b4_execution_quote") or {}
                        )

                    latency_ms = int((time.perf_counter() - t1) * 1000.0)
                    if execution_service is not None:
                        bookkeeping_handler = getattr(
                            execution_service, "handle_post_execute_bookkeeping", None
                        )
                        if callable(bookkeeping_handler):
                            await bookkeeping_handler(
                                self,
                                opp,
                                res,
                                bn=bn,
                                latency_ms=latency_ms,
                                mode="auto",
                            )
                        else:
                            await ExecutionService.handle_post_execute_bookkeeping(
                                execution_service,
                                self,
                                opp,
                                res,
                                bn=bn,
                                latency_ms=latency_ms,
                                mode="auto",
                            )
                    else:
                        await self._record_exec(res, opp, latency_ms=latency_ms, mode="auto")
                        if res.ok and (not res.dry_run) and getattr(res, "submitted", False):
                            self._last_submitted_block = bn
                            self.metrics.last_submitted_block = bn
                finally:
                    if sizing_binding_applied:
                        try:
                            if had_size_mult:
                                decision.size_mult = original_size_mult
                            else:
                                delattr(decision, "size_mult")
                            if had_borrow_mult:
                                decision.borrow_mult = original_borrow_mult
                            else:
                                delattr(decision, "borrow_mult")
                        except (AttributeError, TypeError):
                            # The decision object may be immutable; the binding
                            # path already failed closed before execution in that case.
                            pass
        finally:
            execution_service = getattr(self, "_execution_service", None)
            if execution_service is not None:
                execution_service.restore_operator_overrides(
                    self,
                    old_gas_mode=old_gas_mode,
                    old_send_mode=old_send_mode,
                )
            else:
                self.cfg.execution.gas_mode = old_gas_mode
                self.metrics.gas_mode = old_gas_mode
                self.cfg.execution.send_mode = old_send_mode
                self.metrics.send_mode = old_send_mode
