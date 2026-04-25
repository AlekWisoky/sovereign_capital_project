from __future__ import annotations

from typing import Any

from ..fioa import FIOARuntime
from ..llm_inl import LLMINLRuntime
from ..superstructure import SuperstructureRuntime

_SAFE_RUNTIME_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def initialize_optional_overlay_runtimes(runtime: Any, cfg: Any, data_dir: str) -> None:
    """Initialize optional overlay runtimes on an existing RuntimeBundle.

    This is intentionally non-hot-path constructor logic that preserves the
    RuntimeBundle attribute contract while reducing constructor concentration.
    """

    runtime._super = None
    try:
        runtime._super = SuperstructureRuntime(
            cfg=getattr(cfg.execution, "superstructure", None),
            chain=cfg.chain.name,
            data_dir=data_dir,
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._super = None

    runtime._fioa = None
    try:
        runtime._fioa = FIOARuntime(
            cfg=getattr(cfg.execution, "fioa", None),
            chain=cfg.chain.name,
            data_dir=data_dir,
            superstructure=getattr(runtime, "_super", None),
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._fioa = None

    runtime._inl = None
    try:
        runtime._inl = LLMINLRuntime(
            cfg=getattr(cfg.execution, "llm_inl", None),
            chain=cfg.chain.name,
            data_dir=data_dir,
            fioa=getattr(runtime, "_fioa", None),
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._inl = None
