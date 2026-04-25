"""AQE — Autonomous Quant Engine (additive).

This package is intentionally modular and optional. The core DeFi arb runtime
continues to operate without AQE enabled.

Phase plan (see README VISION):
- Phase 1: QMIX/VDN coordination baseline
- Phase 2: intrinsic curiosity + RND
- Phase 3: adaptive exploration controller
- Phase 4: harmony layer + budget allocator
- Phase 5+: arbitrage/MEV/meta-strategy layers
"""

from .core.smmae_engine import SMMAEEngine, SMMAEConfig

# Additive optional layers
try:  # pragma: no cover
    from .spread import SpreadEngine, SpreadEngineConfig
    from .coordination import SharedFeatureBus
    from .execution import ExecutionOrchestrator
    from .capital import CapitalAllocator
    from .funding import FundingArbStrategy
except ImportError:  # pragma: no cover
    SpreadEngine = None  # type: ignore
    SpreadEngineConfig = None  # type: ignore
    SharedFeatureBus = None  # type: ignore
    ExecutionOrchestrator = None  # type: ignore
    CapitalAllocator = None  # type: ignore
    FundingArbStrategy = None  # type: ignore

__all__ = [
    "SMMAEEngine",
    "SMMAEConfig",
    "SpreadEngine",
    "SpreadEngineConfig",
    "SharedFeatureBus",
    "ExecutionOrchestrator",
    "CapitalAllocator",
    "FundingArbStrategy",
]
