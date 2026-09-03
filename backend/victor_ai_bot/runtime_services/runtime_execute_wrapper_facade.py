from __future__ import annotations

import importlib
import time
from typing import Any, Awaitable, Callable, Tuple

from ..decision_identity import ensure_decision_identity
from ..identity import attach_identity, new_execution_identity
from ..execution import try_execute_opportunity
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

    def _ensure_execution_identity(self, opp: Any, decision: Any) -> None:
        if decision is None or opp is None:
            return
        try:
            identity = ensure_decision_identity(
                opp,
                decision,
                chain_name=str(getattr(getattr(self, "cfg", None).chain, "name", "default")),
            )
            execution_identity = new_execution_identity(identity)
            attach_identity(opp, execution_identity)
            meta = getattr(opp, "meta", None)
            if isinstance(meta, dict):
                lineage = meta.setdefault("canonical_lineage", {})
                if isinstance(lineage, dict):
                    lineage.update(execution_identity.to_dict())
        except (AttributeError, TypeError, ValueError):
            return

    async def _run_prepared_auto_execution(
        self,
        *,
        opp: Any,
        bn: int,
        decision: Any,
        prep: AutoExecutionDispatchContext,
    ) -> None:
        self._ensure_execution_identity(opp, decision)
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
                t1 = time.perf_counter()
                span = LatencySpan()

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
                            execution_service, self, opp, decision, _core
                        )
                else:
                    res = await _core()

                identity = getattr(opp, "identity", None)
                if identity is not None:
                    attach_identity(res, identity)

                latency_ms = int((time.perf_counter() - t1) * 1000.0)
                if execution_service is not None:
                    bookkeeping_handler = getattr(execution_service, "handle_post_execute_bookkeeping", None)
                    if callable(bookkeeping_handler):
                        await bookkeeping_handler(
                            self, opp, res, bn=bn, latency_ms=latency_ms, mode="auto"
                        )
                    else:
                        await ExecutionService.handle_post_execute_bookkeeping(
                            execution_service, self, opp, res, bn=bn, latency_ms=latency_ms, mode="auto"
                        )
                else:
                    await self._record_exec(res, opp, latency_ms=latency_ms, mode="auto")
                    if res.ok and (not res.dry_run) and getattr(res, "submitted", False):
                        self._last_submitted_block = bn
                        self.metrics.last_submitted_block = bn
        finally:
            execution_service = getattr(self, "_execution_service", None)
            if execution_service is not None:
                execution_service.restore_operator_overrides(
                    self, old_gas_mode=old_gas_mode, old_send_mode=old_send_mode
                )
            else:
                self.cfg.execution.gas_mode = old_gas_mode
                self.metrics.gas_mode = old_gas_mode
                self.cfg.execution.send_mode = old_send_mode
                self.metrics.send_mode = old_send_mode
