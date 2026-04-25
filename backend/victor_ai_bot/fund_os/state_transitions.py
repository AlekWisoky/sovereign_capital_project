from __future__ import annotations

import time
from typing import Any, Dict, List

from ..domain_errors import InvalidTransitionError
from .health_states import HealthState, normalize_health_state

_ALLOWED: Dict[str, set[str]] = {
    HealthState.LIVE.value: {
        HealthState.CAPPED_LIVE.value,
        HealthState.DEGRADED.value,
        HealthState.OBSERVE_ONLY.value,
        HealthState.DISABLED.value,
        HealthState.QUARANTINED.value,
    },
    HealthState.CAPPED_LIVE.value: {
        HealthState.LIVE.value,
        HealthState.DEGRADED.value,
        HealthState.OBSERVE_ONLY.value,
        HealthState.DISABLED.value,
        HealthState.QUARANTINED.value,
    },
    HealthState.DEGRADED.value: {
        HealthState.CAPPED_LIVE.value,
        HealthState.OBSERVE_ONLY.value,
        HealthState.DISABLED.value,
        HealthState.QUARANTINED.value,
    },
    HealthState.OBSERVE_ONLY.value: {
        HealthState.CAPPED_LIVE.value,
        HealthState.LIVE.value,
        HealthState.DISABLED.value,
        HealthState.QUARANTINED.value,
    },
    HealthState.DISABLED.value: {HealthState.OBSERVE_ONLY.value, HealthState.CAPPED_LIVE.value},
    HealthState.QUARANTINED.value: {HealthState.OBSERVE_ONLY.value, HealthState.DISABLED.value},
}


def apply_transition(
    *,
    family: str,
    current_state: str,
    target_state: str,
    actor: str,
    reason_code: str,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    cur = normalize_health_state(current_state)
    tgt = normalize_health_state(target_state)
    if cur == tgt:
        return {
            "family": str(family),
            "from_state": cur,
            "to_state": tgt,
            "actor": str(actor or "system"),
            "reason_code": str(reason_code or "noop"),
            "details": dict(details or {}),
            "ts_ms": int(time.time() * 1000),
            "changed": False,
        }
    allowed = _ALLOWED.get(cur, set())
    if tgt not in allowed:
        raise InvalidTransitionError(
            f"invalid transition {cur}->{tgt}", reason_code="invalid_transition"
        )
    return {
        "family": str(family),
        "from_state": cur,
        "to_state": tgt,
        "actor": str(actor or "system"),
        "reason_code": str(reason_code or "state_transition"),
        "details": dict(details or {}),
        "ts_ms": int(time.time() * 1000),
        "changed": True,
    }


def append_transition(
    history: List[Dict[str, Any]] | None, transition: Dict[str, Any]
) -> List[Dict[str, Any]]:
    out = list(history or [])
    out.append(dict(transition))
    return out[-200:]
