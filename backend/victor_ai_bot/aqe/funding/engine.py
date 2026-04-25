from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from victor_ai_bot.engine_control.models import EngineOpportunity
from .carry_model import carry_horizon_score
from .risk_model import funding_risk_adjustment


@dataclass
class FundingArbConfig:
    enabled: bool = False
    min_rate_diff: float = 0.0001
    enter_window_seconds: int = 600  # enter within 10m of funding time
    max_positions: int = 3


class FundingTracker:
    """Tracks funding data (best-effort)."""

    def __init__(self):
        self.last: Dict[str, Any] = {}

    def observe(self, *, rows: List[Dict[str, Any]]) -> None:
        self.last = {"ts": int(time.time()), "rows": list(rows)[:200]}

    def snapshot(self) -> Dict[str, Any]:
        return dict(self.last)


class FundingArbStrategy:
    """Funding carry engine with conservative horizon, fee, and liquidation modeling."""

    engine_type = 'funding_arb'

    def __init__(self, *, cfg: Optional[FundingArbConfig] = None):
        self.cfg = cfg or FundingArbConfig()
        self.last_scan: Dict[str, Any] = {}

    def scan(self, *, funding_rows: List[Dict[str, Any]], chain: str = 'offchain', chain_id: int = 0, regime: str = 'balanced') -> List[EngineOpportunity]:
        if not bool(self.cfg.enabled):
            self.last_scan = {"ts": int(time.time()), "enabled": False}
            return []
        rows = list(funding_rows or [])
        by_sym: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            sym = str(r.get("symbol") or "")
            if sym:
                by_sym.setdefault(sym, []).append(r)
        intents: List[EngineOpportunity] = []
        for sym, rs in by_sym.items():
            if len(rs) < 2:
                continue
            hi = max(rs, key=lambda x: float(x.get("funding_rate") or 0.0))
            lo = min(rs, key=lambda x: float(x.get("funding_rate") or 0.0))
            diff = float(hi.get("funding_rate") or 0.0) - float(lo.get("funding_rate") or 0.0)
            if abs(diff) < float(self.cfg.min_rate_diff):
                continue
            hours_to_funding = float(min(float(self.cfg.enter_window_seconds) / 3600.0, float(hi.get('hours_to_funding') or 8.0), float(lo.get('hours_to_funding') or 8.0)))
            basis_bps = float(hi.get('basis_bps') or 0.0) - float(lo.get('basis_bps') or 0.0)
            fee_bps = float(hi.get('fee_bps') or 6.0) + float(lo.get('fee_bps') or 6.0)
            carry = carry_horizon_score(rate_diff=abs(diff), hours_to_funding=hours_to_funding, basis_bps=basis_bps, venue_fee_bps=fee_bps)
            risk = funding_risk_adjustment(
                leverage=float(max(1.0, hi.get('leverage') or 1.0, lo.get('leverage') or 1.0)),
                collateral_efficiency=float(min(float(hi.get('collateral_efficiency') or 0.9), float(lo.get('collateral_efficiency') or 0.9))),
                liquidation_buffer_pct=float(min(float(hi.get('liquidation_buffer_pct') or 12.0), float(lo.get('liquidation_buffer_pct') or 12.0))),
                divergence_score=float(abs(basis_bps) / 100.0),
            )
            capital = float(hi.get('notional_usd') or lo.get('notional_usd') or 2000.0)
            gross = capital * max(0.0, float(carry['carry_per_period']))
            realized = gross * max(0.0, 1.0 - float(risk['risk_penalty_ratio']))
            conf = max(0.35, min(0.92, 0.58 + abs(diff) * 35.0 - float(risk['risk_penalty_ratio'])))
            flags = []
            if float(risk['liquidation_penalty']) > 0.02:
                flags.append('liquidation_risk')
            if float(risk['collateral_penalty']) > 0.01:
                flags.append('collateral_risk')
            if abs(basis_bps) > 35.0:
                flags.append('basis_risk')
            intents.append(EngineOpportunity(
                opportunity_id=f'funding:{sym}:{hi.get("venue")}:{lo.get("venue")}',
                engine_type=self.engine_type,
                strategy_family='funding_arb',
                route_family=f'funding_arb|{sym}|{hi.get("venue")}|{lo.get("venue")}',
                chain=str(chain),
                chain_id=int(chain_id),
                expected_profit_usd=round(gross, 6),
                expected_realized_profit_usd=round(realized, 6),
                capital_required_usd=round(capital, 6),
                inventory_requirements={sym: round(capital / max(1.0, float(hi.get('mark_price') or lo.get('mark_price') or 1.0)), 8)},
                confidence=round(conf, 6),
                regime=str(regime),
                latency_sensitivity=max(0.15, min(0.85, 1.0 / max(1.0, hours_to_funding))),
                risk_flags=flags,
                lifecycle_eligibility='paper' if flags else 'capped_live',
                policy_eligibility='capped_live' if not flags else 'paper',
                venues=[str(hi.get('venue') or ''), str(lo.get('venue') or '')],
                metadata={'symbol': sym, 'short_venue': str(hi.get('venue') or ''), 'long_venue': str(lo.get('venue') or ''), 'rate_diff': diff, 'carry': carry, 'risk': risk, 'hours_to_funding': hours_to_funding},
            ))
        intents.sort(key=lambda x: abs(float(x.expected_realized_profit_usd)), reverse=True)
        intents = intents[: int(self.cfg.max_positions)]
        self.last_scan = {"ts": int(time.time()), "n": len(intents)}
        return intents
