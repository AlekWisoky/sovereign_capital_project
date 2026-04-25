from __future__ import annotations

from typing import Dict


STAGES = ["sandbox", "paper", "shadow_live", "capped_live", "production", "degraded", "retired"]


def next_stage(*, robustness: float, validation_ok: bool, live_ok: bool) -> str:
    if robustness < 0.35:
        return "retired"
    if not validation_ok:
        return "sandbox"
    if robustness >= 0.80 and live_ok:
        return "production"
    if robustness >= 0.70:
        return "capped_live"
    if robustness >= 0.55:
        return "shadow_live"
    return "paper"
