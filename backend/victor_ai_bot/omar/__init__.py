"""First-class OMAR learning subsystem.

OMAR remains downstream of decision selection and upstream of governance/execution.
It learns from settled real outcomes and may only provide bounded recommendations.
"""

from .config import OmarConfig
from .runtime import OmarRuntime

try:
    from .production_lineage_bridge import install_production_lineage_bridge
    from .lifecycle_bridge import install_omar_lifecycle_hooks
    from ..runtime_services.canonical_settlement_interface import (
        install_canonical_settlement_bridge,
        install_canonical_settlement_interface,
    )

    install_canonical_settlement_interface()
    install_canonical_settlement_bridge()
    install_production_lineage_bridge()
    install_omar_lifecycle_hooks()
except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
    pass

__all__ = ["OmarConfig", "OmarRuntime"]
