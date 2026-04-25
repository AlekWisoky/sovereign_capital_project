from __future__ import annotations

import os
from typing import Any

from ..aqe.arbitrage import ArbitrageRuntime
from ..aqe.mev import MEVRuntime, MEVGuard
from ..aqe.meta import MetaStrategyRuntime
from ..pathing import canonical_data_dir

_SAFE_RUNTIME_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def initialize_optional_family_runtimes(runtime: Any, cfg: Any, data_dir: str) -> None:
    """Initialize non-v1 additive family runtimes on an existing RuntimeBundle.

    This is intentionally non-hot-path and preserves the legacy RuntimeBundle
    attribute contract while reducing constructor concentration.
    """

    # Phase 5: Cross-venue arbitrage engine (additive, optional).
    # v1 production focus default: disable non-atomic modules.
    runtime._arbitrage = None
    try:
        if (
            str(getattr(cfg.execution, "v1_focus", "flashloan_atomic") or "flashloan_atomic")
            != "flashloan_atomic"
        ):
            runtime._arbitrage = ArbitrageRuntime(cfg.execution.arbitrage)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._arbitrage = None

    # Phase 6: MEV module (additive, defensive-first).
    runtime._mev = None
    runtime._mev_guard = None
    try:
        mev_cfg = getattr(cfg.execution, "mev", None)
        # v1 production focus default: disable MEV module.
        if (
            str(getattr(cfg.execution, "v1_focus", "flashloan_atomic") or "flashloan_atomic")
            == "flashloan_atomic"
        ):
            mev_cfg = None
        if mev_cfg is not None and bool(getattr(mev_cfg, "enabled", False)):
            ws_urls = list(getattr(mev_cfg, "ws", []) or []) or list(
                getattr(cfg.chain, "ws", []) or []
            )
            rpc_http = cfg.chain.rpc_read[0] if getattr(cfg.chain, "rpc_read", None) else ""
            if not rpc_http and getattr(cfg.chain, "rpc_send", None):
                rpc_http = cfg.chain.rpc_send[0]
            if ws_urls and rpc_http:
                runtime._mev = MEVRuntime(cfg=mev_cfg, ws_urls=ws_urls, rpc_http_url=rpc_http)
                runtime._mev_guard = MEVGuard(cfg=mev_cfg, mev_runtime=runtime._mev)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._mev = None
        runtime._mev_guard = None

    # Phase 7: Meta strategy generator (additive, optional).
    runtime._meta = None
    try:
        meta_cfg = getattr(cfg.execution, "meta", None)
        allow_auto = bool(int(os.environ.get("VICTOR_META_ALLOW_AUTO_APPLY", "0") or "0"))
        # v1 production scope default: do not enable meta evolution unless explicitly requested.
        if (
            str(getattr(cfg.execution, "v1_focus", "flashloan_atomic") or "flashloan_atomic")
            == "flashloan_atomic"
        ):
            # still allow meta if explicitly enabled and controls permit
            pass
        if meta_cfg is not None and bool(getattr(meta_cfg, "enabled", False)):
            meta_data_dir = canonical_data_dir(os.environ.get("VICTOR_DATA_DIR", data_dir))
            os.makedirs(meta_data_dir, exist_ok=True)
            runtime._meta = MetaStrategyRuntime(
                chain_name=cfg.chain.name,
                data_dir=meta_data_dir,
                cfg=meta_cfg,
                allow_auto_apply=allow_auto,
            )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._meta = None
