from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .formulas import alpha_score, net_profit_usd
from .thresholds import AdaptiveThresholds, ThresholdConfig
from .types import OpportunityType, SpreadOpportunity


def _mid(bid: float, ask: float) -> float:
    if bid <= 0.0 or ask <= 0.0:
        return 0.0
    return 0.5 * (float(bid) + float(ask))


@dataclass
class SpreadEngineConfig:
    enabled: bool = False
    max_opps: int = 50
    default_volume_usd: float = 250.0
    fee_bps: float = 10.0
    gas_usd: float = 3.0
    vol_risk_usd: float = 0.5
    min_alpha: float = 0.10


class BaseSpreadEngine:
    def scan(self, *, state: Dict[str, Any]) -> List[SpreadOpportunity]:
        return []


class SpotSpotCrossExchangeArbitrageEngine(BaseSpreadEngine):
    def scan(self, *, state: Dict[str, Any]) -> List[SpreadOpportunity]:
        quotes: List[Dict[str, Any]] = list(state.get("quotes", []) or [])
        if not quotes:
            return []
        # group by symbol
        by_sym: Dict[str, List[Dict[str, Any]]] = {}
        for q in quotes:
            sym = str(q.get("symbol") or "")
            if not sym:
                continue
            by_sym.setdefault(sym, []).append(q)

        out: List[SpreadOpportunity] = []
        for sym, rows in by_sym.items():
            # best ask venue to buy
            buy = min(rows, key=lambda r: float(r.get("ask") or 0.0) if float(r.get("ask") or 0.0) > 0 else 1e18)
            # best bid venue to sell
            sell = max(rows, key=lambda r: float(r.get("bid") or 0.0))
            bid = float(sell.get("bid") or 0.0)
            ask = float(buy.get("ask") or 0.0)
            if bid <= 0.0 or ask <= 0.0:
                continue
            spread = (bid - ask) / ask
            if spread <= 0:
                continue
            vol = float(state.get("default_volume_usd") or 250.0)
            fees = vol * (float(state.get("fee_bps") or 10.0) / 10_000.0) * 2.0
            gas = float(state.get("gas_usd") or 0.0)
            prof = net_profit_usd(spread=spread, volume=vol, fees_usd=fees, gas_usd=gas, vol_risk_usd=float(state.get("vol_risk_usd") or 0.0))
            out.append(
                SpreadOpportunity(
                    opp_id=f"spotspot:{sym}:{buy.get('venue')}:{sell.get('venue')}",
                    opp_type=OpportunityType.SPOT_SPOT,
                    buy_venue=str(buy.get("venue") or ""),
                    sell_venue=str(sell.get("venue") or ""),
                    symbol=sym,
                    spread=float(spread),
                    volume=float(vol),
                    fees_usd=float(fees),
                    gas_usd=float(gas),
                    vol_risk_usd=float(state.get("vol_risk_usd") or 0.0),
                    profit_usd=float(prof),
                )
            )
        return out


class SpotFuturesArbitrageEngine(BaseSpreadEngine):
    def scan(self, *, state: Dict[str, Any]) -> List[SpreadOpportunity]:
        quotes = list(state.get("quotes", []) or [])
        if not quotes:
            return []
        # use rows tagged product
        spot = [q for q in quotes if str(q.get("product") or "spot") == "spot"]
        fut = [q for q in quotes if str(q.get("product") or "") in {"futures", "perp"}]
        if not spot or not fut:
            return []
        by_sym_spot: Dict[str, List[Dict[str, Any]]] = {}
        by_sym_fut: Dict[str, List[Dict[str, Any]]] = {}
        for q in spot:
            by_sym_spot.setdefault(str(q.get("symbol") or ""), []).append(q)
        for q in fut:
            by_sym_fut.setdefault(str(q.get("symbol") or ""), []).append(q)
        out: List[SpreadOpportunity] = []
        for sym in sorted(set(by_sym_spot.keys()) & set(by_sym_fut.keys())):
            srow = max(by_sym_spot[sym], key=lambda r: _mid(float(r.get("bid") or 0.0), float(r.get("ask") or 0.0)))
            frow = max(by_sym_fut[sym], key=lambda r: _mid(float(r.get("bid") or 0.0), float(r.get("ask") or 0.0)))
            smid = _mid(float(srow.get("bid") or 0.0), float(srow.get("ask") or 0.0))
            fmid = _mid(float(frow.get("bid") or 0.0), float(frow.get("ask") or 0.0))
            if smid <= 0 or fmid <= 0:
                continue
            spread = (fmid - smid) / smid
            # funding can flip sign; treat funding_rate as bonus for shorting positive funding
            fr = float(frow.get("funding_rate") or 0.0)
            vol = float(state.get("default_volume_usd") or 250.0)
            fees = vol * (float(state.get("fee_bps") or 10.0) / 10_000.0) * 2.0
            gas = float(state.get("gas_usd") or 0.0)
            prof = net_profit_usd(spread=spread, volume=vol, fees_usd=fees, gas_usd=gas, vol_risk_usd=float(state.get("vol_risk_usd") or 0.0))
            # funding adjust: if fr>0, short perp earns funding; if fr<0, long earns funding.
            funding_adjust = float(abs(fr))
            a = alpha_score(
                profit_usd=float(prof),
                capital_usd=float(vol),
                funding_adjust=funding_adjust,
                liquidity_penalty=0.0,
                volatility_penalty=float(state.get("volatility_penalty", 0.0) or 0.0),
                latency_penalty=float(state.get("latency_penalty", 0.0) or 0.0),
                transfer_penalty=float(state.get("transfer_penalty", 0.0) or 0.0),
            )
            out.append(
                SpreadOpportunity(
                    opp_id=f"spotfut:{sym}:{srow.get('venue')}:{frow.get('venue')}",
                    opp_type=OpportunityType.SPOT_FUTURES,
                    buy_venue=str(srow.get("venue") or ""),
                    sell_venue=str(frow.get("venue") or ""),
                    symbol=sym,
                    spread=float(spread),
                    volume=float(vol),
                    fees_usd=float(fees),
                    gas_usd=float(gas),
                    vol_risk_usd=float(state.get("vol_risk_usd") or 0.0),
                    profit_usd=float(prof),
                    alpha=float(a),
                    meta={"spot_mid": smid, "fut_mid": fmid, "funding_rate": fr},
                )
            )
        return out


class FuturesFuturesArbitrageEngine(BaseSpreadEngine):
    def scan(self, *, state: Dict[str, Any]) -> List[SpreadOpportunity]:
        quotes = [q for q in (state.get("quotes") or []) if str(q.get("product") or "") in {"futures", "perp"}]
        if not quotes:
            return []
        by_sym: Dict[str, List[Dict[str, Any]]] = {}
        for q in quotes:
            sym = str(q.get("symbol") or "")
            if sym:
                by_sym.setdefault(sym, []).append(q)
        out: List[SpreadOpportunity] = []
        for sym, rows in by_sym.items():
            if len(rows) < 2:
                continue
            buy = min(rows, key=lambda r: float(r.get("ask") or 0.0) if float(r.get("ask") or 0.0) > 0 else 1e18)
            sell = max(rows, key=lambda r: float(r.get("bid") or 0.0))
            bid = float(sell.get("bid") or 0.0)
            ask = float(buy.get("ask") or 0.0)
            if bid <= 0.0 or ask <= 0.0:
                continue
            spread = (bid - ask) / ask
            if spread <= 0:
                continue
            vol = float(state.get("default_volume_usd") or 250.0)
            fees = vol * (float(state.get("fee_bps") or 10.0) / 10_000.0) * 2.0
            prof = net_profit_usd(spread=spread, volume=vol, fees_usd=fees, gas_usd=float(state.get("gas_usd") or 0.0), vol_risk_usd=float(state.get("vol_risk_usd") or 0.0))
            out.append(
                SpreadOpportunity(
                    opp_id=f"futfut:{sym}:{buy.get('venue')}:{sell.get('venue')}",
                    opp_type=OpportunityType.FUTURES_FUTURES,
                    buy_venue=str(buy.get("venue") or ""),
                    sell_venue=str(sell.get("venue") or ""),
                    symbol=sym,
                    spread=float(spread),
                    volume=float(vol),
                    fees_usd=float(fees),
                    gas_usd=float(state.get("gas_usd") or 0.0),
                    vol_risk_usd=float(state.get("vol_risk_usd") or 0.0),
                    profit_usd=float(prof),
                )
            )
        return out


class FundingRateArbitrageEngine(BaseSpreadEngine):
    def scan(self, *, state: Dict[str, Any]) -> List[SpreadOpportunity]:
        quotes = [q for q in (state.get("quotes") or []) if str(q.get("product") or "") in {"futures", "perp"}]
        if not quotes:
            return []
        # pick extremes by funding
        by_sym: Dict[str, List[Dict[str, Any]]] = {}
        for q in quotes:
            sym = str(q.get("symbol") or "")
            if sym:
                by_sym.setdefault(sym, []).append(q)
        out: List[SpreadOpportunity] = []
        for sym, rows in by_sym.items():
            if len(rows) < 2:
                continue
            hi = max(rows, key=lambda r: float(r.get("funding_rate") or 0.0))
            lo = min(rows, key=lambda r: float(r.get("funding_rate") or 0.0))
            fr_hi = float(hi.get("funding_rate") or 0.0)
            fr_lo = float(lo.get("funding_rate") or 0.0)
            if abs(fr_hi - fr_lo) < 1e-9:
                continue
            vol = float(state.get("default_volume_usd") or 250.0)
            # treat funding difference as expected edge per period
            spread = float(fr_hi - fr_lo)
            prof = net_profit_usd(spread=spread, volume=vol, fees_usd=vol * (float(state.get("fee_bps") or 10.0) / 10_000.0), gas_usd=float(state.get("gas_usd") or 0.0))
            out.append(
                SpreadOpportunity(
                    opp_id=f"funding:{sym}:{hi.get('venue')}:{lo.get('venue')}",
                    opp_type=OpportunityType.FUNDING_ARB,
                    buy_venue=str(lo.get("venue") or ""),
                    sell_venue=str(hi.get("venue") or ""),
                    symbol=sym,
                    spread=float(spread),
                    volume=float(vol),
                    profit_usd=float(prof),
                    meta={"funding_hi": fr_hi, "funding_lo": fr_lo},
                )
            )
        return out


class CEXDEXArbitrageEngine(BaseSpreadEngine):
    """Scaffold: requires unified dex pools."""

    def scan(self, *, state: Dict[str, Any]) -> List[SpreadOpportunity]:
        # If state provides dex_prices: {symbol: price_usd}
        quotes = list(state.get("quotes", []) or [])
        dex_prices: Dict[str, float] = dict(state.get("dex_prices", {}) or {})
        if not quotes or not dex_prices:
            return []
        out: List[SpreadOpportunity] = []
        for q in quotes:
            sym = str(q.get("symbol") or "")
            if not sym or sym not in dex_prices:
                continue
            c_mid = _mid(float(q.get("bid") or 0.0), float(q.get("ask") or 0.0))
            d = float(dex_prices.get(sym) or 0.0)
            if c_mid <= 0 or d <= 0:
                continue
            # If CEX mid > DEX, buy on DEX, sell on CEX
            spread = (c_mid - d) / d
            if spread <= 0:
                continue
            vol = float(state.get("default_volume_usd") or 250.0)
            prof = net_profit_usd(spread=spread, volume=vol, fees_usd=vol * (float(state.get("fee_bps") or 10.0) / 10_000.0), gas_usd=float(state.get("gas_usd") or 0.0), transfer_usd=float(state.get("transfer_usd") or 0.0))
            out.append(
                SpreadOpportunity(
                    opp_id=f"cexdex:{sym}:{q.get('venue')}",
                    opp_type=OpportunityType.CEX_DEX,
                    buy_venue="dex",
                    sell_venue=str(q.get("venue") or ""),
                    symbol=sym,
                    spread=float(spread),
                    volume=float(vol),
                    profit_usd=float(prof),
                    meta={"cex_mid": c_mid, "dex_price": d},
                )
            )
        return out


class CrossChainPlaceholderEngine(BaseSpreadEngine):
    def scan(self, *, state: Dict[str, Any]) -> List[SpreadOpportunity]:
        return []


class SpreadEngine:
    def __init__(self, *, cfg: Optional[SpreadEngineConfig] = None, thresholds: Optional[AdaptiveThresholds] = None):
        self.cfg = cfg or SpreadEngineConfig()
        self.thresholds = thresholds or AdaptiveThresholds(cfg=ThresholdConfig(base_alpha=float(self.cfg.min_alpha)))

        self.engines: List[BaseSpreadEngine] = [
            SpotSpotCrossExchangeArbitrageEngine(),
            SpotFuturesArbitrageEngine(),
            FuturesFuturesArbitrageEngine(),
            FundingRateArbitrageEngine(),
            CEXDEXArbitrageEngine(),
            CrossChainPlaceholderEngine(),
        ]

        self.last_scan: Dict[str, Any] = {}

    def scan(self, *, state: Dict[str, Any], regime: str = "unknown", stress: Optional[Dict[str, Any]] = None, aggressiveness: str = "LOW") -> List[SpreadOpportunity]:
        if not bool(self.cfg.enabled):
            self.last_scan = {"ts": int(time.time()), "enabled": False}
            return []

        # Provide normalized parameters to engines
        st = dict(state or {})
        st.setdefault("default_volume_usd", float(self.cfg.default_volume_usd))
        st.setdefault("fee_bps", float(self.cfg.fee_bps))
        st.setdefault("gas_usd", float(self.cfg.gas_usd))
        st.setdefault("vol_risk_usd", float(self.cfg.vol_risk_usd))

        opps: List[SpreadOpportunity] = []
        safe_scan_exceptions = (AttributeError, KeyError, TypeError, ValueError)
        for e in self.engines:
            try:
                opps.extend(e.scan(state=st))
            except safe_scan_exceptions:
                continue

        # Compute alpha for those missing it
        for o in opps:
            if float(o.alpha) == 0.0:
                o.alpha = alpha_score(profit_usd=float(o.profit_usd), capital_usd=float(max(1e-9, o.volume)))

        thr = self.thresholds.dynamic_threshold(regime=str(regime), stress=stress or {}, aggressiveness=str(aggressiveness))
        out = [o for o in opps if float(o.alpha) > float(thr)]
        out.sort(key=lambda x: (float(x.alpha), float(x.profit_usd)), reverse=True)
        out = out[: int(self.cfg.max_opps)]

        self.last_scan = {"ts": int(time.time()), "n": len(out), "threshold": float(thr), "regime": str(regime), "aggressiveness": str(aggressiveness)}
        return out
