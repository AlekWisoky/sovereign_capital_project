"""FIOA (FIU-inspired Operational Independence & Autonomy) layer.

This package is an **add-only governance overlay** that wraps execution and
high-risk state mutations with:
  - operational scope validation
  - resource limits (capital/risk)
  - escalation + safe-mode triggers
  - audit trail

The core flash-loan arbitrage engine remains immutable.
"""

from .config import FIOAConfig
from .runtime import FIOARuntime

__all__ = ["FIOAConfig", "FIOARuntime"]
