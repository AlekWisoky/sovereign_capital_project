"""Phase 6: Defensive-first MEV monitor + evaluator + private routing hooks.

This module is *additive* and does not change core architecture.
Default is disabled. When enabled in `execution.mev`, it can:
- monitor mempool for relevant pending txs
- estimate MEV risk (sandwich/backrun probability proxy)
- block unsafe public submissions (safety rail)
- optionally recommend private/protected submission

Hard policy: no predatory MEV execution (no sandwich attacks).
"""

from .runtime import MEVRuntime
from .guard import MEVGuard
