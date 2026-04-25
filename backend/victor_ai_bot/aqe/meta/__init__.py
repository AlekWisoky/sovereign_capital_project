"""Phase 7: Autonomous Strategy Generation Layer (Meta-Evolution).

Additive module that:
- detects lightweight market/runtime regimes from internal telemetry
- proposes new strategy candidates (config mutations) within safe bounds
- maintains a self-expanding module registry on disk
- can operate in observe/suggest/auto modes (auto requires explicit allow)

This module does NOT mutate core engine architecture.
"""

from .runtime import MetaStrategyRuntime
