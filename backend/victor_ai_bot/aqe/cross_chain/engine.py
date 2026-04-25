from __future__ import annotations

from typing import Any, Dict, List

from victor_ai_bot.engine_control.models import EngineOpportunity

from .bridge_model import bridge_risk_model
from .inventory_model import chain_inventory_gate


class CrossChainArbitrageEngine:
    engine_type = 'cross_chain_arb'

    def scan(self, *, spreads: List[Dict[str, Any]], chain_inventory: Dict[str, float], bridge_quotes: Dict[str, Dict[str, Any]], regime: str = 'balanced') -> List[EngineOpportunity]:
        out: List[EngineOpportunity] = []
        for row in list(spreads or []):
            src = str(row.get('src_chain') or '')
            dst = str(row.get('dst_chain') or '')
            symbol = str(row.get('symbol') or '')
            gross_spread = float(row.get('spread_ratio') or 0.0)
            capital = float(row.get('capital_required_usd') or 0.0)
            if not src or not dst or src == dst or capital <= 0.0 or gross_spread <= 0.0:
                continue
            bridge = dict((bridge_quotes or {}).get(f'{src}->{dst}') or {})
            risk = bridge_risk_model(
                finality_seconds=float(bridge.get('finality_seconds') or 1800.0),
                bridge_fee_bps=float(bridge.get('bridge_fee_bps') or 18.0),
                timeout_probability=float(bridge.get('timeout_probability') or 0.08),
            )
            inv = chain_inventory_gate(inventory_by_chain=chain_inventory, src_chain=src, dst_chain=dst, capital_required_usd=capital)
            expected = capital * gross_spread
            realized = expected * max(0.0, 1.0 - float(risk['penalty_ratio']))
            flags = ['bridge_risk', 'settlement_risk']
            if not bool(inv['ok']):
                flags.append('inventory_thin')
            confidence = max(0.20, min(0.85, 0.58 + gross_spread * 3.0 - float(risk['penalty_ratio'])))
            out.append(EngineOpportunity(
                opportunity_id=f'cross-chain:{symbol}:{src}:{dst}',
                engine_type=self.engine_type,
                strategy_family='cross_chain_arb',
                route_family=f'cross_chain_arb|{src}|{dst}|{symbol}',
                chain=src,
                chain_id=int(row.get('chain_id') or 0),
                expected_profit_usd=round(expected, 6),
                expected_realized_profit_usd=round(realized, 6),
                capital_required_usd=round(capital, 6),
                inventory_requirements={src: round(capital, 6), dst: round(capital * 0.35, 6)},
                confidence=round(confidence, 6),
                regime=str(regime),
                latency_sensitivity=min(1.0, float(bridge.get('finality_seconds') or 1800.0) / 3600.0),
                risk_flags=flags,
                lifecycle_eligibility='paper',
                policy_eligibility='observe_only' if not bool(inv['ok']) else 'capped_live',
                venues=[src, dst, str(bridge.get('bridge') or 'bridge')],
                metadata={'symbol': symbol, 'bridge': bridge, 'inventory_gate': inv, 'class': str(row.get('class') or 'prepositioned_capital_arb')},
            ))
        out.sort(key=lambda o: (-float(o.expected_realized_profit_usd), str(o.opportunity_id)))
        return out
