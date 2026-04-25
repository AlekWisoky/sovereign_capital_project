from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

from .action_policy import universal_action_policy


def universal_action_to_opportunity(action: Dict[str, Any]) -> Any:
    policy = universal_action_policy(action)
    if not bool(policy.get("allowed")):
        return SimpleNamespace(
            id=str((action or {}).get("action_id") or ""),
            expected_profit_usd=float((action or {}).get("expected_profit_usd") or 0.0),
            expected_realized_profit_usd=0.0,
            route_family=str((action or {}).get("route_family") or ""),
            meta={
                "drop_reason": str(policy.get("reason") or ""),
                "strategy_family": str((action or {}).get("family") or ""),
                "engine_type": str((action or {}).get("engine_type") or ""),
            },
            venues=list((action or {}).get("venues") or []),
            token_path=list((action or {}).get("token_path") or []),
            capital_required_usd=float((action or {}).get("capital_required_usd") or 0.0),
            confidence=float((action or {}).get("confidence") or 0.0),
        )
    return SimpleNamespace(
        id=str((action or {}).get("action_id") or ""),
        expected_profit_usd=float((action or {}).get("expected_profit_usd") or 0.0),
        expected_realized_profit_usd=float(
            (action or {}).get("expected_realized_profit_usd") or 0.0
        ),
        route_family=str((action or {}).get("route_family") or ""),
        meta={
            "strategy_family": str((action or {}).get("family") or ""),
            "engine_type": str((action or {}).get("engine_type") or ""),
            "capital_required_usd": float((action or {}).get("capital_required_usd") or 0.0),
        },
        venues=list((action or {}).get("venues") or []),
        token_path=list((action or {}).get("token_path") or []),
        capital_required_usd=float((action or {}).get("capital_required_usd") or 0.0),
        confidence=float((action or {}).get("confidence") or 0.0),
    )
