from __future__ import annotations

from typing import Any, Dict


def default_event_bus_config() -> Dict[str, Any]:
    return {
        "enabled": False,
        "backend": "memory",
        "topics": ["market_data", "features", "strategy_actions", "execution_results"],
    }
