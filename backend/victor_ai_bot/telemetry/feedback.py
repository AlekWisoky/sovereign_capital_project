from __future__ import annotations

from typing import Any, Dict, List

from .aggregates import summarize_agents, summarize_realization


def compute_feedback(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "realization": summarize_realization(events),
        "agents": summarize_agents(events),
    }
