"""First-class OMAR learning subsystem.

OMAR remains downstream of decision selection and upstream of governance/execution.
It learns from settled real outcomes and may only provide bounded recommendations.
"""

from .config import OmarConfig
from .runtime import OmarRuntime

try:
    from .lifecycle_bridge import install_omar_lifecycle_hooks

    install_omar_lifecycle_hooks()
except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
    pass

__all__ = ["OmarConfig", "OmarRuntime"]
