from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable


class HealthState(str, Enum):
    LIVE = "live"
    DEGRADED = "degraded"
    OBSERVE_ONLY = "observe_only"
    CAPPED_LIVE = "capped_live"
    DISABLED = "disabled"
    QUARANTINED = "quarantined"


HEALTH_PRIORITY: Dict[str, int] = {
    HealthState.LIVE.value: 5,
    HealthState.CAPPED_LIVE.value: 4,
    HealthState.DEGRADED.value: 3,
    HealthState.OBSERVE_ONLY.value: 2,
    HealthState.DISABLED.value: 1,
    HealthState.QUARANTINED.value: 0,
}


def normalize_health_state(
    value: str | None, *, default: str = HealthState.OBSERVE_ONLY.value
) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in HEALTH_PRIORITY else str(default)


def worst_health_state(states: Iterable[str]) -> str:
    selected = normalize_health_state(None)
    selected_rank = HEALTH_PRIORITY[selected]
    for state in states:
        norm = normalize_health_state(state)
        rank = HEALTH_PRIORITY[norm]
        if rank < selected_rank:
            selected = norm
            selected_rank = rank
    return selected
