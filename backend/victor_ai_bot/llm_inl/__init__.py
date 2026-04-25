"""LLM-mediated Interactive Narrative Layer (LLM-INL).

This package is an **additive overlay**. It must never prevent the core bot
from starting.
"""

from .config import LLMINLConfig
from .runtime import LLMINLRuntime

__all__ = ["LLMINLConfig", "LLMINLRuntime"]
