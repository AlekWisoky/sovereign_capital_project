from __future__ import annotations

import time

_SAFE_BUDGET_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeBudgetFacade:
    """Execution amount / gas-budget compatibility facade.

    This isolates non-hot-path amount resolution and daily gas-budget bookkeeping
    helpers away from RuntimeBundle's orchestration monolith while preserving
    the existing compatibility surface used by the loop and receipt paths.
    """

    def _resolve_amount_in(self) -> int:
        service = getattr(self, "_execution_service", None)
        return service.resolve_amount_in(self) if service is not None else 0

    def _reset_budget_day_if_needed(self) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        if day != getattr(self, "_budget_day", ""):
            self._budget_day = day
            self._gas_spent_today_wei = 0
            self._pending_gas_est_wei = 0

    def _gas_budget_remaining_wei(self) -> int:
        """Remaining daily gas budget in wei.

        If budget is disabled (0), return a large sentinel.
        """
        self._reset_budget_day_if_needed()
        try:
            budget = int(getattr(self.cfg.execution, "daily_gas_budget_wei", "0") or "0")
        except _SAFE_BUDGET_EXCEPTIONS:
            budget = 0
        if budget <= 0:
            return 10**30
        used = int(getattr(self, "_gas_spent_today_wei", 0)) + int(
            getattr(self, "_pending_gas_est_wei", 0)
        )
        return max(0, budget - used)
