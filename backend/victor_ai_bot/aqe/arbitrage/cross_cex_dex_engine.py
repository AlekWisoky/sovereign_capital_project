from __future__ import annotations

from typing import Any, Dict, List

from victor_ai_bot.engine_control.models import EngineOpportunity


def _mid(bid: float, ask: float) -> float:
    if bid <= 0.0 or ask <= 0.0:
        return 0.0
    return 0.5 * (bid + ask)


class CrossCEXDEXArbitrageEngine:
    """Inventory-aware, settlement-aware cross CEX/DEX planner.

    Produces normalized opportunities suitable for capture scoring.
    Does not execute; it emits conservative opportunities/intents.
    """

    engine_type = 'cross_cex_dex'

    def scan(self, *, quotes: List[Dict[str, Any]], dex_prices: Dict[str, float], dex_depths: Dict[str, float] | None = None, venue_inventory: Dict[str, Dict[str, float]] | None = None, transfer_cost_bps: float = 12.0, settlement_seconds: float = 180.0, chain: str = 'ethereum', chain_id: int = 1, regime: str = 'balanced') -> List[EngineOpportunity]:
        dex_depths = dex_depths or {}
        venue_inventory = venue_inventory or {}
        out: List[EngineOpportunity] = []
        for q in list(quotes or []):
            sym = str(q.get('symbol') or '')
            if not sym or sym not in dex_prices:
                continue
            bid = float(q.get('bid') or 0.0)
            ask = float(q.get('ask') or 0.0)
            c_mid = _mid(bid, ask)
            d_mid = float(dex_prices.get(sym) or 0.0)
            if c_mid <= 0.0 or d_mid <= 0.0:
                continue
            side = 'buy_dex_sell_cex' if c_mid > d_mid else 'buy_cex_sell_dex'
            gross_spread = abs(c_mid - d_mid) / max(d_mid, 1e-9)
            cex_venue = str(q.get('venue') or 'cex')
            cex_inv = float(((venue_inventory.get(cex_venue) or {}).get(sym) or 0.0))
            dex_inv = float(((venue_inventory.get('dex') or {}).get(sym) or 0.0))
            inventory_ok = max(cex_inv, dex_inv)
            depth_usd = min(float(dex_depths.get(sym) or 0.0), max(50.0, float(q.get('depth_usd') or 0.0))) or 250.0
            capital_required = max(25.0, depth_usd * 0.35)
            transfer_penalty = capital_required * (float(transfer_cost_bps) / 10_000.0)
            settlement_penalty = capital_required * min(0.0025, max(0.0, float(settlement_seconds) / 400_000.0))
            leg_risk_penalty = capital_required * (0.0015 if inventory_ok > 0 else 0.0100)
            expected_profit = capital_required * gross_spread
            realized = expected_profit - transfer_penalty - settlement_penalty - leg_risk_penalty
            if realized <= 0.0:
                continue
            conf = max(0.35, min(0.92, 0.55 + gross_spread * 4.0 - settlement_penalty / max(capital_required, 1.0)))
            flags = []
            if inventory_ok <= 0.0:
                flags.append('inventory_thin')
            if settlement_seconds >= 600:
                flags.append('settlement_risk')
            if gross_spread < 0.003:
                flags.append('thin_edge')
            route_family = f'cross_cex_dex|{side}|{cex_venue}|dex'
            out.append(EngineOpportunity(
                opportunity_id=f'cross-cex-dex:{sym}:{cex_venue}:{side}',
                engine_type=self.engine_type,
                strategy_family='cross_cex_dex',
                route_family=route_family,
                chain=str(chain),
                chain_id=int(chain_id),
                expected_profit_usd=round(expected_profit, 6),
                expected_realized_profit_usd=round(realized, 6),
                capital_required_usd=round(capital_required, 6),
                inventory_requirements={sym: round(capital_required / max(d_mid, 1e-9), 8)},
                confidence=round(conf, 6),
                regime=str(regime),
                latency_sensitivity=min(1.0, float(settlement_seconds) / 600.0),
                risk_flags=flags,
                lifecycle_eligibility='paper' if 'inventory_thin' in flags else 'capped_live',
                policy_eligibility='capped_live' if 'inventory_thin' not in flags else 'observe_only',
                venues=[cex_venue, 'dex'],
                metadata={
                    'symbol': sym,
                    'side': side,
                    'cex_mid': c_mid,
                    'dex_mid': d_mid,
                    'transfer_penalty_usd': round(transfer_penalty, 6),
                    'settlement_penalty_usd': round(settlement_penalty, 6),
                    'leg_risk_penalty_usd': round(leg_risk_penalty, 6),
                    'inventory_available': round(inventory_ok, 8),
                },
            ))
        out.sort(key=lambda o: (-float(o.expected_realized_profit_usd), str(o.opportunity_id)))
        return out
