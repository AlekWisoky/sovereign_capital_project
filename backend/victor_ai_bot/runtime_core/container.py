from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .coordinator import MultiRuntimeBundle, RuntimeBundle


@dataclass
class RuntimeContainer:
    runtime: Any

    @property
    def active_runtime(self) -> Any:
        rt = self.runtime
        if isinstance(rt, MultiRuntimeBundle):
            return rt._runtimes.get(rt._active_chain) or rt
        return rt


def build_runtime_container(runtime: Any) -> RuntimeContainer:
    return RuntimeContainer(runtime=runtime)
