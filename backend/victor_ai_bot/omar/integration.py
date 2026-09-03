from __future__ import annotations

from typing import Any, Dict

from .config import OmarConfig
from .runtime import OmarRuntime

_ACTIVE_OMAR_RUNTIME: OmarRuntime | None = None


def active_omar_runtime() -> OmarRuntime | None:
    """Return the single OMAR runtime used by production learning callbacks."""
    return _ACTIVE_OMAR_RUNTIME


def make_omar_from_settings(settings: Dict[str, Any], chain_name: str) -> OmarRuntime:
    global _ACTIVE_OMAR_RUNTIME
    cfg_raw = (settings or {}).get("execution", {}).get("superstructure", {}).get("omar", {}) or {}
    cfg = OmarConfig(
        **{k: cfg_raw[k] for k in cfg_raw.keys() if k in OmarConfig.__dataclass_fields__}
    )
    runtime = OmarRuntime(cfg=cfg, chain_name=chain_name)
    _ACTIVE_OMAR_RUNTIME = runtime
    if cfg.enabled:
        runtime.start()
    return runtime
