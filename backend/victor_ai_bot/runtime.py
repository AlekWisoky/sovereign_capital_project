from __future__ import annotations

"""Public runtime shell.

This module intentionally stays thin and re-exports the runtime coordinator and
bootstrap helpers from runtime_core for backward compatibility.
"""

from .runtime_core import (
    RuntimeBundle,
    MultiRuntimeBundle,
    RuntimeContainer,
    build_runtime,
    load_runtime_configs,
    make_runtime_lifespan,
)
from .aqe.arbitrage.runtime import ArbitrageRuntime
from .behaveagent.runtime import BehaveAgentRuntime
from .fioa.runtime import FIOARuntime
from .governance.runtime import GovernanceRuntime
from .llm_inl.runtime import LLMINLRuntime
from .aqe.meta.runtime import MetaStrategyRuntime
from .aqe.mev.runtime import MEVRuntime
from .omar.runtime import OmarRuntime
from .analytics.quicksight.runtime import QuickSightAnalyticsRuntime
from .superstructure.runtime import SuperstructureRuntime
from .treasury.runtime import TreasuryRuntime

__all__ = [
    "RuntimeBundle",
    "MultiRuntimeBundle",
    "RuntimeContainer",
    "build_runtime",
    "load_runtime_configs",
    "make_runtime_lifespan",
    "ArbitrageRuntime",
    "BehaveAgentRuntime",
    "FIOARuntime",
    "GovernanceRuntime",
    "LLMINLRuntime",
    "MetaStrategyRuntime",
    "MEVRuntime",
    "OmarRuntime",
    "QuickSightAnalyticsRuntime",
    "SuperstructureRuntime",
    "TreasuryRuntime",
]
