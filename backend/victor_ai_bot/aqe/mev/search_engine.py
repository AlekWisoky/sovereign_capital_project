from __future__ import annotations

from typing import Any, Dict, List

from victor_ai_bot.engine_control.models import EngineOpportunity


class MEVSearchEngine:
    engine_type = 'mev_search'

    def search(self, *, mev_state: Dict[str, Any], base_opportunities: List[Any], regime: str = 'balanced', chain: str = 'ethereum', chain_id: int = 1) -> List[EngineOpportunity]:
        pending = list(mev_state.get('sample_pending') or [])
        high_risk = float(mev_state.get('high_risk_ratio') or 0.0)
        out: List[EngineOpportunity] = []
        for tx in pending[:8]:
            tags = set(tx.get('tags') or [])
            if 'dex_like' not in tags and not str(tx.get('sel') or '').startswith('0x'):
                continue
            expected = 4.0 + float(tx.get('value_wei') or 0) / 1e18 * 0.02
            realized = expected * max(0.25, 0.85 - high_risk * 0.35)
            risk_flags = ['private_send']
            conf = max(0.35, min(0.90, 0.58 + (0.15 if 'sandwich_risk' not in tags else -0.10)))
            lifecycle = 'capped_live' if conf >= 0.68 else 'paper'
            out.append(EngineOpportunity(
                opportunity_id=f"mev:{tx.get('hash')}",
                engine_type=self.engine_type,
                strategy_family='mev_search',
                route_family=f"mev_search|backrun_protection|{tx.get('to')}",
                chain=chain,
                chain_id=int(chain_id),
                expected_profit_usd=round(expected, 6),
                expected_realized_profit_usd=round(realized, 6),
                capital_required_usd=25.0,
                inventory_requirements={},
                confidence=round(conf, 6),
                regime=str(regime),
                latency_sensitivity=0.95,
                risk_flags=risk_flags,
                lifecycle_eligibility=lifecycle,
                policy_eligibility='capped_live',
                venues=['private_relay'],
                metadata={'tx_hash': tx.get('hash'), 'candidate_type': 'backrun_or_protection'},
            ))
        for base in list(base_opportunities or [])[:4]:
            meta = dict(getattr(base, 'meta', {}) or {}) if isinstance(getattr(base, 'meta', None), dict) else {}
            mev_risk = float((((meta.get('aqe') or {}) if isinstance(meta.get('aqe'), dict) else {}).get('mev_risk') or 0.0))
            if mev_risk < 0.55:
                continue
            expected = float(getattr(base, 'expected_profit_usd', 0.0) or 0.0)
            if expected > 1000:
                expected /= 1_000_000.0
            realized = expected * max(0.25, 0.9 - mev_risk * 0.4)
            out.append(EngineOpportunity(
                opportunity_id=f"mev-protect:{getattr(base, 'id', '')}",
                engine_type=self.engine_type,
                strategy_family='mev_search',
                route_family='mev_search|protect_existing_route',
                chain=chain,
                chain_id=int(chain_id),
                expected_profit_usd=round(expected, 6),
                expected_realized_profit_usd=round(realized, 6),
                capital_required_usd=50.0,
                inventory_requirements={},
                confidence=round(max(0.5, 0.82 - mev_risk * 0.2), 6),
                regime=str(regime),
                latency_sensitivity=0.98,
                risk_flags=['private_send'],
                lifecycle_eligibility='capped_live',
                policy_eligibility='capped_live',
                venues=['private_relay'],
                metadata={'base_opportunity_id': getattr(base, 'id', ''), 'candidate_type': 'route_protection'},
            ))
        out.sort(key=lambda o: (-float(o.expected_realized_profit_usd), str(o.opportunity_id)))
        return out
