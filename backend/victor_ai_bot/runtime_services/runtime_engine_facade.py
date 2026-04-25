from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..deploy_mode import is_public_mode, public_broadcast_override_enabled

_SAFE_ENGINE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
)


class RuntimeEngineFacade:
    """Normalized engine-scan compatibility facade.

    This isolates RuntimeBundle's non-hot-path engine input assembly and scan
    invocation away from the main tick loop while preserving the existing
    local-failure semantics: ordinary shape/state issues degrade quietly,
    while unexpected bugs still escape to the process-boundary containment in
    runtime_legacy._loop.
    """

    def _engine_quotes(self) -> List[Dict[str, Any]]:
        if getattr(self, "_arbitrage", None) is None:
            return []
        state = self._arbitrage.state()
        return list(state.get("quotes") or [])

    @staticmethod
    def _engine_funding_rows(quotes_engine: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            q
            for q in list(quotes_engine or [])
            if str(q.get("product") or "") in {"futures", "perp"}
            and q.get("funding_rate") is not None
        ]

    def _engine_dex_inputs(self) -> Tuple[Dict[str, float], Dict[str, float]]:
        dex_prices: Dict[str, float] = {}
        dex_depths: Dict[str, float] = {}
        for so in list(getattr(self, "_spread_opps", []) or [])[:50]:
            meta_so = (
                dict(getattr(so, "meta", {}) or {}) if isinstance(getattr(so, "meta", None), dict) else {}
            )
            sym = str(getattr(so, "symbol", "") or meta_so.get("symbol") or "")
            if sym and "dex_price" in meta_so:
                dex_prices[sym] = float(meta_so.get("dex_price") or 0.0)
            if sym and "dex_depth_usd" in meta_so:
                dex_depths[sym] = float(meta_so.get("dex_depth_usd") or 0.0)
        return dex_prices, dex_depths

    def _engine_bridge_spreads(self) -> List[Dict[str, Any]]:
        bridge_spreads: List[Dict[str, Any]] = []
        if not getattr(self, "_spread_opps", None):
            return bridge_spreads
        for so in list(self._spread_opps)[:20]:
            try:
                t = str(getattr(so, "opp_type", "") or "")
                if t == "cross_chain":
                    bridge_spreads.append(
                        {
                            "src_chain": str(
                                (getattr(so, "meta", {}) or {}).get("src_chain") or "ethereum"
                            ),
                            "dst_chain": str(
                                (getattr(so, "meta", {}) or {}).get("dst_chain") or "arbitrum"
                            ),
                            "symbol": str(getattr(so, "symbol", "") or ""),
                            "spread_ratio": float(getattr(so, "spread", 0.0) or 0.0),
                            "capital_required_usd": float(getattr(so, "volume", 0.0) or 0.0),
                            "class": "bridge_adjusted_spread_arb",
                            "chain_id": int(getattr(self.cfg.chain, "chain_id", 0) or 0),
                        }
                    )
            except _SAFE_ENGINE_EXCEPTIONS:
                continue
        return bridge_spreads

    @staticmethod
    def _engine_bridge_quotes() -> Dict[str, Dict[str, Any]]:
        return {
            "ethereum->arbitrum": {
                "bridge": "canonical",
                "finality_seconds": 900.0,
                "bridge_fee_bps": 12.0,
                "timeout_probability": 0.05,
            }
        }

    @staticmethod
    def _engine_chain_inventory(treasury_state: Dict[str, Any] | None) -> Dict[str, float]:
        capital = ((treasury_state or {}).get("capital_engine") or {}) if isinstance(treasury_state, dict) else {}
        return {
            "ethereum": float((capital.get("deployable_bankroll_wei") or 0) / 1e18),
            "arbitrum": float((capital.get("experimental_bankroll_wei") or 0) / 1e18),
        }

    def _engine_meta_candidates(self) -> List[Dict[str, Any]]:
        if getattr(self, "_meta", None) is None:
            return []
        return list((self._meta.state() or {}).get("last_candidates") or [])

    def _scan_engine_opportunities(
        self,
        *,
        regime_label: str,
        mev_state: Dict[str, Any] | None,
        base_opportunities: List[Any] | None,
        treasury_state: Dict[str, Any] | None,
    ) -> bool:
        try:
            quotes_engine = self._engine_quotes()
            funding_rows = self._engine_funding_rows(quotes_engine)
            dex_prices, dex_depths = self._engine_dex_inputs()
            self._engine_last = self._engine_service.scan(
                chain=str(self.cfg.chain.name),
                chain_id=int(getattr(self.cfg.chain, "chain_id", 0) or 0),
                regime=str(regime_label or "balanced"),
                quotes=quotes_engine,
                funding_rows=funding_rows,
                dex_prices=dex_prices,
                dex_depths=dex_depths,
                venue_inventory={"dex": {}},
                bridge_spreads=self._engine_bridge_spreads(),
                bridge_quotes=self._engine_bridge_quotes(),
                chain_inventory=self._engine_chain_inventory(treasury_state),
                mev_state=dict(mev_state or {}),
                base_opportunities=list(base_opportunities or []),
                meta_candidates=self._engine_meta_candidates(),
                treasury_state=dict(treasury_state or {}),
                public_mode=bool(is_public_mode() and not public_broadcast_override_enabled()),
            )
            return True
        except _SAFE_ENGINE_EXCEPTIONS:
            return False
