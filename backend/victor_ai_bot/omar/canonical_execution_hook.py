from __future__ import annotations

import inspect
from typing import Any

from .canonical_execution import require_canonical_execution_context
from ..sentry_config import set_sentry_trade_context


def install_canonical_execution_invariant() -> None:
    """Install hard production guards at dispatch and execution boundaries."""
    from victor_ai_bot.runtime_core import RuntimeBundle

    original_dispatch = getattr(RuntimeBundle, "_maybe_dispatch_auto_trade", None)
    if original_dispatch is not None and not getattr(original_dispatch, "_canonical_execution_guard", False):
        def guarded_dispatch(self: Any, *, current_block: int, decision: Any = None) -> bool:
            # brain_mode=off means the DecisionEngine is authoritative; it does
            # not mean "pick the best candidate without a canonical decision".
            if decision is None:
                return False
            return original_dispatch(self, current_block=current_block, decision=decision)

        guarded_dispatch._canonical_execution_guard = True
        RuntimeBundle._maybe_dispatch_auto_trade = guarded_dispatch

    original_execute = getattr(RuntimeBundle, "_execute_auto", None)
    if original_execute is None or getattr(original_execute, "_canonical_execution_guard", False):
        return

    async def guarded_execute(self: Any, opp: Any, bn: int, decision: Any = None) -> Any:
        decision_id, correlation_id = require_canonical_execution_context(
            self, opp, decision, current_block=int(bn)
        )
        set_sentry_trade_context(
            decision_id=decision_id,
            correlation_id=correlation_id,
            opportunity_id=str(getattr(opp, "id", "") or ""),
            route_id=str(getattr(opp, "route_id", "") or ""),
            action=str(getattr(decision, "action", "") or ""),
            mode=str(getattr(getattr(getattr(self, "cfg", None), "execution", None), "brain_mode", "") or ""),
        )
        return await original_execute(self, opp, int(bn), decision)

    guarded_execute._canonical_execution_guard = True
    RuntimeBundle._execute_auto = guarded_execute


# Keep import-time installation idempotent and non-fatal: the invariant itself
# remains explicit and is exercised by production-path tests.
try:
    install_canonical_execution_invariant()
except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
    pass
