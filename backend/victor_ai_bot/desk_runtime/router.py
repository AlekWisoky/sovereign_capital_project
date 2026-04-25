from __future__ import annotations

from typing import Any, Dict

from ..execution_capture.action_router import universal_action_to_opportunity


def route_pod_action(action: Dict[str, Any]) -> Any:
    return universal_action_to_opportunity(action)
