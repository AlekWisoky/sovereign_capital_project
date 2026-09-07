"""OMAR learning subsystem.

OMAR is downstream of the canonical decision and upstream of governance/execution.
It learns only from physically persisted canonical settled outcomes.
"""

from .config import OmarConfig
from .runtime import OmarRuntime

__all__ = ["OmarConfig", "OmarRuntime"]
