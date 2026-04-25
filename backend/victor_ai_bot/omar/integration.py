from __future__ import annotations
from typing import Any, Dict

from .config import OmarConfig
from .runtime import OmarRuntime


def make_omar_from_settings(settings: Dict[str, Any], chain_name: str) -> OmarRuntime:
    cfg_raw = (settings or {}).get("execution", {}).get("superstructure", {}).get("omar", {}) or {}
    cfg = OmarConfig(
        **{k: cfg_raw[k] for k in cfg_raw.keys() if k in OmarConfig.__dataclass_fields__}
    )
    return OmarRuntime(cfg=cfg, chain_name=chain_name)
