from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict


class AgentHealthStatus(str, Enum):
    HEALTHY = 'HEALTHY'
    DEGRADED = 'DEGRADED'
    FAILED = 'FAILED'
    TIMED_OUT = 'TIMED_OUT'
    STALE = 'STALE'


@dataclass
class AgentHealth:
    status: AgentHealthStatus
    last_duration_ms: float = 0.0
    last_error: str = ''
    age_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['status'] = str(self.status.value)
        return d


def classify_health(*, duration_ms: float, ttl_ms: int, ok: bool, error: str = '', age_ms: int = 0) -> AgentHealth:
    if not ok and duration_ms >= float(ttl_ms):
        return AgentHealth(AgentHealthStatus.TIMED_OUT, float(duration_ms), str(error), int(age_ms))
    if not ok:
        return AgentHealth(AgentHealthStatus.FAILED, float(duration_ms), str(error), int(age_ms))
    if age_ms > int(ttl_ms):
        return AgentHealth(AgentHealthStatus.STALE, float(duration_ms), str(error), int(age_ms))
    if duration_ms > float(ttl_ms) * 0.65:
        return AgentHealth(AgentHealthStatus.DEGRADED, float(duration_ms), str(error), int(age_ms))
    return AgentHealth(AgentHealthStatus.HEALTHY, float(duration_ms), str(error), int(age_ms))
