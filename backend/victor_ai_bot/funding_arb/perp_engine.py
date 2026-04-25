from __future__ import annotations

from typing import Any, Dict

from .carry_model import carry_horizon_value
from .risk_model import collateral_risk
from ..execution_capture.universal_actions import UniversalAction


def build_funding_action(*, symbol: str, venue: str, annualized_funding_pct: float, notional_usd: float, hours: float, collateral_efficiency: float, liquidation_buffer_pct: float) -> Dict[str, Any]:
    carry = carry_horizon_value(annualized_funding_pct=annualized_funding_pct, notional_usd=notional_usd, hours=hours, fee_drag_pct=0.08, basis_drag_pct=0.05)
    risk = collateral_risk(collateral_efficiency=collateral_efficiency, liquidation_buffer_pct=liquidation_buffer_pct)
    net = float(carry['netCarryUsd']) * max(0.25, 1.0 - float(risk['riskPenalty']))
    act = UniversalAction(action_id=f'funding-{symbol}-{venue}', family='funding_arb', action_type='carry_trade', route_family='funding_arb', engine_type='funding_arb', chain='offchain', venues=[venue], token_path=[symbol], expected_profit_usd=float(carry['grossCarryUsd']), expected_realized_profit_usd=net, capital_required_usd=notional_usd, confidence=max(0.3, min(0.95, 0.55 + abs(float(annualized_funding_pct))/50.0 - float(risk['riskPenalty']))), lifecycle_stage='paper', metadata={'hours': hours, 'liquidationBufferPct': liquidation_buffer_pct, 'collateralEfficiency': collateral_efficiency})
    return act.to_dict()
