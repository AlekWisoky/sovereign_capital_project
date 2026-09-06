from __future__ import annotations

import asyncio
from typing import Any

from ..omar.canonical_execution import (
    CanonicalExecutionInvariantError,
    require_canonical_execution_context,
)

_SAFE_AUTO_QUEUE_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeAutoQueueFacade:
    """Portfolio-recommendation auto-queue and canonical dispatch facade.

    The queue is populated from the canonical decision. Auto execution must
    consume that decision; it may never fall back to the legacy
    ``brain_mode=off`` best-opportunity selector.
    """

    def _refresh_auto_queue_from_decision(self, decision: Any, *, current_block: int) -> bool:
        try:
            portfolio = getattr(decision, "portfolio", None)
            if not portfolio:
                return False
            self._auto_queue = list(portfolio or [])
            self._auto_queue_block = int(current_block)
            return True
        except _SAFE_AUTO_QUEUE_EXCEPTIONS:
            return False

    def _maybe_dispatch_auto_trade(self, *, current_block: int, decision: Any = None) -> bool:
        """Dispatch only a canonical decision-selected opportunity.

        This method intentionally shadows the historical implementation in
        ``RuntimeDecisionFacade``. The old path selected the highest-profit
        executable candidate whenever ``brain_mode == 'off'`` and could then
        execute with ``decision=None``. Production auto execution now has one
        invariant: no canonical decision, no execution.
        """
        if not self._auto_trading or not self._opps or not self._cb.allow_auto_trading():
            return False
        if self._exec_task is not None and not self._exec_task.done():
            return False

        if decision is None or str(getattr(decision, "action", "")).lower() != "trade":
            return False

        chosen = self._decision_auto_trade_candidate(decision)
        if chosen is None:
            return False

        try:
            chosen, decision = self._apply_omar_to_candidate(
                chosen,
                decision,
                current_block=int(current_block),
            )
            if chosen is None or decision is None:
                return False
            require_canonical_execution_context(
                self,
                chosen,
                decision,
                current_block=int(current_block),
            )
        except CanonicalExecutionInvariantError as exc:
            self._errors.append(f"canonical_execution_invariant:{exc}")
            return False
        except _SAFE_AUTO_QUEUE_EXCEPTIONS:
            return False

        self._exec_task = asyncio.create_task(
            self._execute_auto(chosen, int(current_block), decision=decision)
        )
        return True
