from __future__ import annotations

from typing import Any, Dict


def universal_action_policy(action: Dict[str, Any]) -> Dict[str, Any]:
    family = str((action or {}).get("family") or "")
    conf = float((action or {}).get("confidence") or 0.0)
    thin = float((action or {}).get("expected_realized_profit_usd") or 0.0) <= 0.0
    if thin:
        return {"allowed": False, "reason": "non_positive_realized_edge"}
    if family in {"liquidation_capture", "mev_search", "flash_arb"} and conf < 0.75:
        return {"allowed": False, "reason": "high_speed_family_requires_higher_confidence"}
    return {"allowed": True, "reason": "ok"}
