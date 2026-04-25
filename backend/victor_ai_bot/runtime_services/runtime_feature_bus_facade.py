from __future__ import annotations

import asyncio

from ..caq_kds.bus import BUS

_SAFE_FEATURE_BUS_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeFeatureBusFacade:
    """Unified feature-bus refresh/publication compatibility facade.

    This isolates additive unified-state refresh away from RuntimeBundle's
    legacy tick loop while preserving current semantics:
    - refresh only runs when the feature bus is present
    - typed local failures degrade quietly for the tick
    - unexpected bugs still escape to the process boundary
    """

    def _refresh_unified_feature_bus(self) -> bool:
        try:
            feature_bus = getattr(self, "_feature_bus", None)
            if feature_bus is None:
                return False
            feature_bus.update_from_bus()
            BUS.update("unified", feature_bus.snapshot())
            return True
        except _SAFE_FEATURE_BUS_EXCEPTIONS:
            return False
