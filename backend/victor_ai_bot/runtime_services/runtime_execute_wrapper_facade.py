from __future__ import annotations

import importlib
import time
from typing import Any, Awaitable, Callable, Tuple

from ..execution import try_execute_opportunity
from ..identity import attach_identity, identity_from, new_execution_identity
from ..latency_profiler import LatencySpan
from ..rpc import JsonRpcClient
from .execution_service import ExecutionService
from .runtime_execute_dispatch_facade import AutoExecutionDispatchContext


_DefaultTryExecute = Callable[..., Awaitable[Any]]
_DefaultRpcClient = type[JsonRpcClient]
_DEFAULT_JSON_RPC_CLIENT = JsonRpcClient
_DEFAULT_TRY_EXECUTE = try_execute_opportunity


def _compat_execution_wrapper_symbols() -> Tuple[_DefaultRpcClient, _DefaultTryExecute]:
    """Return the canonical execution-wrapper patch seam.

    Legacy/runtime harnesses historically monkeypatched `victor_ai_bot.runtime_legacy`
    to replace `JsonRpcClient` and `try_execute_opportunity`. The refactor moved the
    hot wrapper into this facade, which broke that compatibility seam.

    We intentionally preserve both seam locations now:
    - patching this facade module continues to work for local extraction tests
    - patching `runtime_legacy` continues to work for compatibility/runtime tests
    """

    rpc_cls = JsonRpcClient
    execute_fn = try_execute_opportunity
    try:
        runtime_legacy = importlib.import_module("victor_ai_bot.runtime_legacy")
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
        return rpc_cls, execute_fn

    legacy_rpc = getattr(runtime_legacy, "JsonRpcClient", _DEFAULT_JSON_RPC_CLIENT)
    legacy_exec = getattr(
        runtime_legacy,
        "try_execute_opportunity",
        _DEFAULT_TRY_EXECUTE,
    )
    if legacy_rpc is not _DEFAULT_JSON_RPC_CLIENT:
        rpc_cls = legacy_rpc
    if legacy_exec is not _DEFAULT_TRY_EXECUTE:
        execute_fn = legacy_exec
    return rpc_cls, execute_fn


class RuntimeExecuteWrapperFacade:
    """Compatibility facade for prepared auto-execution wrapper flow.

    This isolates the prepared RPC execution wrapper and post-execution
    bookkeeping from RuntimeBundle._execute_auto while preserving the
    current execution semantics.
    """

    @staticmethod
    def _ensure_execution_identity(res: Any, decision: Any) -> Any:
        """Bind one execution-attempt identity to the execution result.

        The decision/correlation pair is never regenerated here. Every actual
        execution attempt receives its own execution_id, allowing retries to be
        attributed separately while remaining under the same decision lineage.
        """
        decision_identity = identity_from(decision)
        if (
            decision_identity is None
            or not decision_identity.decision_id
            or not decision_identity.correlation_id
        ):
            return res

        existing = identity_from(res)
        if existing is not None and existing.execution_id:
            execution_identity = existing
        else:
            execution_identity = new_execution_identity(decision_identity)
        attach_identity(res, execution_identity)

        try:
            if isinstance(getattr(res, "plan", None), dict):
                res.plan.setdefault("identity", {}).update(execution_identity.to_dict())
                res.plan.setdefault("lineage", {}).update(execution_identity.to_dict())
        except (AttributeError, TypeError):
            pass
        return res

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
                rpc_client_cls(
                    read_url,
                    timeout_s=10.0,
                    max_concurrency=20,
                    max_batch=50,
                ) as rpc_r,
                rpc_client_cls(
                    send_url,
                    timeout_s=10.0,
                    max_concurrency=10,
                    max_batch=20,
                ) as rpc_s,
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
                    fioa_handler = getattr(
                        execution_service,
                        "handle_fioa_execution_wrapper",
                        None,
                    )
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

                # The execution boundary is the point at which decision identity
                # becomes execution identity. This happens before bookkeeping so
                # every downstream recorder sees the same IDs.
                res = self._ensure_execution_identity(res, decision)
                latency_ms = int((time.perf_counter() - t1) * 1000.0)
                if execution_service is not None:
                    bookkeeping_handler = getattr(
                        execution_service,
                        "handle_post_execute_bookkeeping",
                        None,
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
                    await self._record_exec(
                        res,
                        opp,
                        latency_ms=latency_ms,
                        mode="auto",
                    )
                    if res.ok and (not res.dry_run) and getattr(res, "submitted", False):
                        self._last_submitted_block = bn
                        self.metrics.last_submitted_block = bn
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
