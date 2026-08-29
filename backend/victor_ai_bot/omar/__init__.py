"""First-class OMAR learning subsystem.

OMAR remains downstream of decision selection and upstream of governance/execution.
It learns from settled real outcomes and may only provide bounded recommendations.

The runtime implementation is imported lazily so lineage/bridge modules that do
not require the numerical learning stack remain importable when optional runtime
ML dependencies (for example NumPy on constrained Termux environments) are not
installed yet.
"""

from .config import OmarConfig


def __getattr__(name: str):
    if name == "OmarRuntime":
        from .runtime import OmarRuntime

        return OmarRuntime
    raise AttributeError(name)


try:
    from .production_lineage_bridge import install_production_lineage_bridge
    from .lifecycle_bridge import install_omar_lifecycle_hooks
    from .learning_quality_bridge import install_learning_quality_runtime_hooks
    from ..runtime_services.canonical_settlement_interface import (
        install_canonical_settlement_bridge,
        install_canonical_settlement_interface,
    )

    install_canonical_settlement_interface()
    install_canonical_settlement_bridge()
    install_production_lineage_bridge()
    install_omar_lifecycle_hooks()
    install_learning_quality_runtime_hooks()
except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
    pass

__all__ = ["OmarConfig", "OmarRuntime"]
