from __future__ import annotations

from typing import Any


class RuntimeExecuteEntryFacade:
    """Compatibility facade for the outer auto-execution entry wrapper.

    This isolates the remaining `_execute_auto` entry orchestration from
    `RuntimeBundle` while preserving the current semantics:
    - dispatch preparation and early blocked/no-op returns
    - prepared execution wrapper handoff
    - no double-application of decision sizing in the entry wrapper
    """

    async def _execute_auto_entry(self, *, opp: Any, bn: int, decision: Any = None) -> None:
        prep = await self._prepare_auto_execution_dispatch(
            opp=opp,
            bn=int(bn),
            decision=decision,
        )
        if prep is None:
            return

        prepared_opp = prep.opportunity

        # NOTE: Notional sizing (size_mult * borrow_mult) is applied inside
        # try_execute_opportunity with a safe re-quote path when cache is
        # available. We intentionally avoid pre-scaling here to prevent
        # double-applying size_mult.
        await self._run_prepared_auto_execution(
            opp=prepared_opp,
            bn=int(bn),
            decision=decision,
            prep=prep,
        )
