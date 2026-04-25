from __future__ import annotations

import asyncio

_SAFE_BLOCKSPACE_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeBlockspaceFacade:
    """Blockspace observation compatibility facade.

    This isolates additive blockspace analytics observation away from
    RuntimeBundle's legacy tick loop while preserving current semantics:
    - observation remains analytics-only and non-submission
    - missing blockspace state degrades to a no-op
    - typed local failures degrade quietly for the tick
    - compatibility supports both ``block`` and legacy ``block_number`` kwarg
      spellings for observe_block implementations
    - unexpected bugs still escape to the process boundary
    """

    def _observe_blockspace(
        self,
        *,
        block_number: int,
        basefee_gwei: float,
        priority_gwei: float,
        pending_txs: int,
        mev_risk: float,
    ) -> bool:
        try:
            blockspace = getattr(self, "_blockspace", None)
            if blockspace is None:
                return False
            observe = getattr(blockspace, "observe_block", None)
            if not callable(observe):
                return False
            try:
                observe(
                    block=int(block_number),
                    basefee_gwei=float(basefee_gwei),
                    priority_gwei=float(priority_gwei),
                    pending_txs=int(pending_txs),
                    mev_risk=float(mev_risk),
                )
            except TypeError:
                observe(
                    block_number=int(block_number),
                    basefee_gwei=float(basefee_gwei),
                    priority_gwei=float(priority_gwei),
                    pending_txs=int(pending_txs),
                    mev_risk=float(mev_risk),
                )
            return True
        except _SAFE_BLOCKSPACE_EXCEPTIONS:
            return False
