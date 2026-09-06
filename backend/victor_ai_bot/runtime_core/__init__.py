from ..sentry_config import init_sentry

# Observability is initialized at the runtime-core boundary and remains a no-op
# when SENTRY_DSN is absent or the optional SDK cannot be imported.
init_sentry()

from .bootstrap import attach_runtime, build_runtime, load_runtime_configs, make_runtime_lifespan
from .container import RuntimeContainer
from .coordinator import MultiRuntimeBundle, RuntimeBundle

__all__ = [
    "attach_runtime",
    "build_runtime",
    "load_runtime_configs",
    "make_runtime_lifespan",
    "RuntimeContainer",
    "RuntimeBundle",
    "MultiRuntimeBundle",
]
