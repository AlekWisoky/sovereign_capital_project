from __future__ import annotations

from typing import Any, Dict, List

from .health_monitor import at_risk_accounts
from .oracle_listener import oracle_shock
from ..execution_capture.universal_actions import UniversalAction


def liquidation_opportunities(*, accounts: List[Dict[str, Any]], price_signal: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    risk = oracle_shock(price_signal or {})
    out = []
    for row in at_risk_accounts(accounts):
        bonus = float((row or {}).get('liquidationBonusPct') or 5.0)
        notional = float((row or {}).get('notionalUsd') or 0.0)
        expected = notional * bonus / 100.0
        realized = expected * (0.55 if risk.get('oracleShock') else 0.72)
        act = UniversalAction(action_id=f"liq-{row.get('account','')}" , family='liquidation_capture', action_type='liquidation', route_family='liquidation_capture', engine_type='liquidation_engine', chain=str((row or {}).get('chain') or 'ethereum'), venues=[str((row or {}).get('protocol') or 'protocol')], token_path=[str((row or {}).get('debtAsset') or ''), str((row or {}).get('collateralAsset') or '')], expected_profit_usd=expected, expected_realized_profit_usd=realized, capital_required_usd=float((row or {}).get('repayUsd') or 0.0), loan_source='flashloan', confidence=max(0.45, min(0.95, 0.65 + (0.02 - float((row or {}).get('healthFactor') or 1.0)) * 10.0)), lifecycle_stage='shadow_live', metadata={'protocol': row.get('protocol'), 'healthFactor': row.get('healthFactor'), 'oracleShock': risk.get('oracleShock')})
        out.append(act.to_dict())
    return out
