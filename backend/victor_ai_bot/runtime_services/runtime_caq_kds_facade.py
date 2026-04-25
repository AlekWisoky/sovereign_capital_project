from __future__ import annotations

import asyncio
from typing import List, Sequence

from ..caq_kds.bus import BUS

_SAFE_CAQ_KDS_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeCaqKdsFacade:
    """Compatibility facade for CAQ-KDS DEX scan summary publication.

    This isolates additive operator/learning telemetry publication away from
    RuntimeBundle's orchestration monolith while preserving the current
    semantics:
    - publication remains add-only and non-execution-critical
    - per-opportunity annotation issues are skipped locally
    - typed local publication failures degrade quietly for the tick
    - unexpected bugs still escape to the process boundary
    """

    def _dex_scan_margin_ratios(self, *, opps: Sequence[object]) -> List[float]:
        margin_ratios: List[float] = []
        for opportunity in list(opps or [])[:200]:
            try:
                meta = getattr(opportunity, "meta", None)
                if isinstance(meta, dict):
                    margin_ratio = meta.get("margin_ratio")
                    if margin_ratio is None:
                        brain = meta.get("brain") or {}
                        if isinstance(brain, dict):
                            margin_ratio = brain.get("margin_ratio")
                    if margin_ratio is not None:
                        margin_ratios.append(float(margin_ratio))
            except _SAFE_CAQ_KDS_EXCEPTIONS:
                pass
        return margin_ratios

    def _publish_dex_scan_summary(self, *, opps: Sequence[object]) -> bool:
        try:
            margin_ratios = self._dex_scan_margin_ratios(opps=opps)
            avg_margin_ratio = (
                float(sum(margin_ratios) / len(margin_ratios)) if margin_ratios else 0.0
            )
            BUS.update(
                "dex",
                {
                    "opps_per_block": float(len(opps)),
                    "avg_margin_ratio": float(avg_margin_ratio),
                    "route_fail_rate": float(self._route_fail_rate()),
                },
            )
            return True
        except _SAFE_CAQ_KDS_EXCEPTIONS:
            return False
