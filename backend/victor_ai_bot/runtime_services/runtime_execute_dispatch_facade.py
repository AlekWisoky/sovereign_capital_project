from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ..execution import ExecResult
from .execution_service import ExecutionService

_SAFE_EXECUTE_DISPATCH_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


@dataclass(frozen=True)
class AutoExecutionDispatchContext:
    opportunity: Any
    force_dry: bool
    old_gas_mode: str
    old_send_mode: str
    read_url: str
    send_url: str


class RuntimeExecuteDispatchFacade:
    """Auto-execution dispatch preparation compatibility facade.

    This isolates the pre-RPC execution preparation path away from
    RuntimeBundle._execute_auto while preserving the current semantics for:
    - command-center pause/sandbox/defensive clamping
    - execution-service admission and superstructure preflight
    - temporary operator mode override setup
    - governance pre-execution gating
    - send/read RPC selection
    """

    async def _prepare_auto_execution_dispatch(
        self,
        *,
        opp: Any,
        bn: int,
        decision: Any = None,
    ) -> AutoExecutionDispatchContext | None:
        force_dry = False
        try:
            if getattr(self, "_cc", None) is not None:
                controls = getattr(self._cc, "controls", None)
                if controls is not None and bool(getattr(controls, "paused", False)):
                    res = ExecResult(False, True, "cc_paused", attempted=False)
                    await self._record_exec(res, opp, latency_ms=0, mode="auto")
                    return None
                if controls is not None and bool(getattr(controls, "sandbox_only", False)):
                    force_dry = True
                if controls is not None and (
                    bool(getattr(controls, "defensive_mode", False))
                    or bool(getattr(controls, "reduce_exposure_half", False))
                ):
                    try:
                        if decision is not None:
                            sm = float(getattr(decision, "size_mult", 1.0) or 1.0)
                            bm = float(getattr(decision, "borrow_mult", 1.0) or 1.0)
                            setattr(decision, "size_mult", min(sm, 0.5))
                            setattr(decision, "borrow_mult", min(bm, 1.0))
                    except _SAFE_EXECUTE_DISPATCH_EXCEPTIONS:
                        pass
        except _SAFE_EXECUTE_DISPATCH_EXCEPTIONS:
            pass

        dry_run = bool(self.cfg.execution.dry_run or force_dry)
        execution_service = getattr(self, "_execution_service", None)

        if execution_service is not None:
            admission_handler = getattr(execution_service, "handle_auto_trade_admission", None)
            if callable(admission_handler):
                admission = admission_handler(self, opp, decision, force_dry_run=dry_run)
            else:
                admission = ExecutionService.handle_auto_trade_admission(
                    execution_service,
                    self,
                    opp,
                    decision,
                    force_dry_run=dry_run,
                )
            opp = getattr(admission, "opportunity", opp)
            blocked_result = getattr(admission, "blocked_result", None)
            if blocked_result is not None:
                await self._record_exec(blocked_result, opp, latency_ms=0, mode="auto")
                return None

        if execution_service is not None:
            super_handler = getattr(execution_service, "handle_superstructure_pre_execute", None)
            if callable(super_handler):
                super_result = super_handler(self, opp, decision, force_dry_run=dry_run)
            else:
                super_result = ExecutionService.handle_superstructure_pre_execute(
                    execution_service,
                    self,
                    opp,
                    decision,
                    force_dry_run=dry_run,
                )
            opp = getattr(super_result, "opportunity", opp)
            super_enabled = bool(getattr(super_result, "super_enabled", False))
            old_gas_mode = str(
                getattr(super_result, "old_gas_mode", self.cfg.execution.gas_mode)
                or self.cfg.execution.gas_mode
            )
            old_send_mode = str(
                getattr(super_result, "old_send_mode", self.cfg.execution.send_mode)
                or self.cfg.execution.send_mode
            )
            blocked_result = getattr(super_result, "blocked_result", None)
            if blocked_result is not None:
                await self._record_exec(blocked_result, opp, latency_ms=0, mode="auto")
                return None
        else:
            super_enabled = False
            old_gas_mode = str(self.cfg.execution.gas_mode)
            old_send_mode = str(self.cfg.execution.send_mode)

        if decision is not None and (not super_enabled):
            try:
                gas_mode = str(getattr(decision, "gas_mode", "") or "")
                if gas_mode in {"standard", "fast", "instant"}:
                    self.cfg.execution.gas_mode = gas_mode
                    self.metrics.gas_mode = gas_mode
            except _SAFE_EXECUTE_DISPATCH_EXCEPTIONS:
                pass

        if execution_service is not None:
            override_handler = getattr(execution_service, "apply_operator_overrides", None)
            if callable(override_handler):
                opp, force_dry, _override_old_gas_mode, _override_old_send_mode = override_handler(
                    self,
                    opp,
                    force_dry_run=force_dry,
                )
                old_gas_mode = str(_override_old_gas_mode or old_gas_mode)
                old_send_mode = str(_override_old_send_mode or old_send_mode)

        send_url = self.rpc_manager.best_send()
        if str(getattr(self.cfg.execution, "send_mode", "public")) in {"private", "protected_rpc"}:
            send_url = self.rpc_manager.best_private() or send_url
        read_url = self.rpc_manager.best_read()
        if not send_url or not read_url:
            return None

        if execution_service is not None:
            gov_handler = getattr(execution_service, "handle_governance_pre_execute", None)
            if callable(gov_handler):
                gov_result = gov_handler(
                    self,
                    opp,
                    bn,
                    decision,
                    force_dry_run=dry_run,
                )
            else:
                gov_result = ExecutionService.handle_governance_pre_execute(
                    execution_service,
                    self,
                    opp,
                    bn,
                    decision,
                    force_dry_run=dry_run,
                )
            opp = getattr(gov_result, "opportunity", opp)
            blocked_result = getattr(gov_result, "blocked_result", None)
            if blocked_result is not None:
                await self._record_exec(blocked_result, opp, latency_ms=0, mode="auto")
                return None

        return AutoExecutionDispatchContext(
            opportunity=opp,
            force_dry=bool(force_dry),
            old_gas_mode=str(old_gas_mode),
            old_send_mode=str(old_send_mode),
            read_url=str(read_url),
            send_url=str(send_url),
        )
