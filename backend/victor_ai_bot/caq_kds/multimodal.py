from __future__ import annotations

import math
import time
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional

from .bus import BUS
from .knowledge_graph import GRAPH, RAG


_SAFE_EMBED_EXCEPTIONS = (TypeError, ValueError)
_SAFE_GRAPH_CONTEXT_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _stable_hash(s: str) -> int:
    h = hashlib.blake2b(s.encode("utf-8", errors="ignore"), digest_size=8).digest()
    return int.from_bytes(h, "little", signed=False)


def _hash_embed(feats: Dict[str, float], dim: int = 64) -> List[float]:
    """Fast fixed-size embedding via feature hashing.

    This is intentionally simple and dependency-free.
    """
    vec = [0.0] * int(dim)
    for k, v in (feats or {}).items():
        try:
            idx = _stable_hash(str(k)) % dim
            vec[idx] += float(v)
        except _SAFE_EMBED_EXCEPTIONS:
            continue
    # normalize
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [float(x / norm) for x in vec]


def _empty_graph_context(*, degraded: bool, error_code: str = "", detail: str = "") -> Dict[str, Any]:
    return {
        "anchors": [],
        "edge_count": 0,
        "edges": [],
        "embedding": [],
        "novelty": 0.0,
        "degraded": bool(degraded),
        "error_code": str(error_code or ""),
        "error": str(detail or ""),
    }


@dataclass
class FusionConfig:
    dim: int = 64
    # decay horizons (seconds)
    stale_after_s: float = 20.0
    # regime classification thresholds
    high_vol_th: float = 0.85
    high_gas_th: float = 0.75


@dataclass
class GlobalMarketState:
    ts: float
    features: Dict[str, float]
    regime: str
    vol_cluster: int
    embedding: List[float]
    context: Dict[str, Any] = field(default_factory=dict)  # C_t
    raw: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ts": float(self.ts),
            "regime": str(self.regime),
            "vol_cluster": int(self.vol_cluster),
            "features": dict(self.features or {}),
            "embedding": list(self.embedding or []),
            "context": dict(self.context or {}),
            "raw": dict(self.raw or {}),
        }


class MarketFusionEngine:
    """Market Multi-Modal Fusion Engine → outputs S_global.

    Inputs (optional, via MarketDataBus buckets):
      - cex: orderbook/funding summaries
      - dex: on-chain swap/arbitrage summaries
      - mev: mempool/relay stats
      - sentiment: social/news sentiment (optional)
      - macro: macro indicators (optional)
      - wallets: on-chain wallet behavior (optional)
      - liq: liquidation streams (optional)
      - reliability: performance quantification outputs (optional)

    Output:
      - Unified market features + fixed-length embedding (S_global.embedding)
      - Regime label + volatility cluster id
    """

    def __init__(self, cfg: Optional[FusionConfig] = None):
        self.cfg = cfg or FusionConfig()
        self._last_regime = "unknown"
        self._vol_ema = 0.0

    def _bucket(self, snap: Dict[str, Any], name: str) -> Tuple[float, Dict[str, Any]]:
        b = (snap or {}).get(name) or {}
        ts = float(b.get("ts", 0.0) or 0.0)
        data = b.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        return ts, data

    def fuse(self, *, local_state: Dict[str, Any]) -> GlobalMarketState:
        now = time.time()
        snap = BUS.snapshot()

        # --- gather per-modal summaries (stale-safe) ---
        cex_ts, cex = self._bucket(snap, "cex")
        dex_ts, dex = self._bucket(snap, "dex")
        mev_ts, mev = self._bucket(snap, "mev")
        sent_ts, sent = self._bucket(snap, "sentiment")
        macro_ts, macro = self._bucket(snap, "macro")
        wallets_ts, wallets = self._bucket(snap, "wallets")
        liq_ts, liq = self._bucket(snap, "liq")
        rel_ts, rel = self._bucket(snap, "reliability")
        kds_ts, kds = self._bucket(snap, "kds")

        def fresh(ts: float) -> bool:
            return (now - float(ts or 0.0)) <= float(self.cfg.stale_after_s)

        # --- feature assembly (all features float) ---
        feats: Dict[str, float] = {}

        # local decision features (always present)
        mr = float(local_state.get("margin_ratio", 0.0) or 0.0)
        gr = float(local_state.get("gas_ratio", 0.0) or 0.0)
        legs = float(local_state.get("legs", 2) or 2)
        p_succ = float(local_state.get("p_success", 0.75) or 0.75)
        ev = float(local_state.get("ev_wei", 0.0) or 0.0)

        feats.update({
            "local.margin_ratio": mr,
            "local.gas_ratio": gr,
            "local.legs": legs,
            "local.p_success": p_succ,
            "local.ev": ev / 1e18,  # scale
        })

        # DEX summary features
        if fresh(dex_ts):
            feats["dex.opps_per_block"] = float(dex.get("opps_per_block", 0.0) or 0.0)
            feats["dex.avg_margin_ratio"] = float(dex.get("avg_margin_ratio", 0.0) or 0.0)
            feats["dex.route_fail_rate"] = float(dex.get("route_fail_rate", 0.0) or 0.0)

        # CEX orderbook/funding features
        if fresh(cex_ts):
            feats["cex.spread_bps"] = float(cex.get("spread_bps", 0.0) or 0.0)
            feats["cex.depth_usd"] = float(cex.get("depth_usd", 0.0) or 0.0) / 1e6
            feats["cex.imbalance"] = float(cex.get("imbalance", 0.0) or 0.0)
            feats["cex.funding_bps"] = float(cex.get("funding_bps", 0.0) or 0.0)
            feats["cex.funding_change_bps"] = float(cex.get("funding_change_bps", 0.0) or 0.0)

        # MEV mempool features
        if fresh(mev_ts):
            feats["mev.pending_rate"] = float(mev.get("pending_rate", 0.0) or 0.0)
            feats["mev.router_flow"] = float(mev.get("router_flow", 0.0) or 0.0)
            feats["mev.sandwich_risk"] = float(mev.get("sandwich_risk", 0.0) or 0.0)

        # sentiment/news
        if fresh(sent_ts):
            feats["sent.score"] = float(sent.get("score", 0.0) or 0.0)

        # macro
        if fresh(macro_ts):
            feats["macro.risk_on"] = float(macro.get("risk_on", 0.0) or 0.0)
            feats["macro.usd_strength"] = float(macro.get("usd_strength", 0.0) or 0.0)

        # wallets
        if fresh(wallets_ts):
            feats["wallets.flow"] = float(wallets.get("flow", 0.0) or 0.0)
            feats["wallets.whale"] = float(wallets.get("whale", 0.0) or 0.0)

        # liquidations
        if fresh(liq_ts):
            feats["liq.intensity"] = float(liq.get("intensity", 0.0) or 0.0)

        # reliability
        if fresh(rel_ts):
            feats["rel.reliability"] = float(rel.get("reliability", 0.0) or 0.0)
            feats["rel.drawdown"] = float(rel.get("max_drawdown", 0.0) or 0.0)
            feats["rel.sharpe"] = float(rel.get("sharpe", 0.0) or 0.0)

        # Phase 13: self-evolution (KDS)
        if fresh(kds_ts):
            feats["kds.active"] = float(kds.get("active", 0.0) or 0.0)
            feats["kds.last_conf"] = float(kds.get("last_conf", 0.0) or 0.0)
            feats["kds.explore_budget"] = float(kds.get("explore_budget", 0.0) or 0.0)

        # --- regime / vol clustering ---
        # volatility proxy: combine mempool, funding change, and p_success inversely
        vol_proxy = _clip(
            0.40 * abs(feats.get("cex.funding_change_bps", 0.0)) / 10.0 +
            0.25 * abs(feats.get("mev.sandwich_risk", 0.0)) +
            0.20 * (1.0 - _clip(p_succ, 0.0, 1.0)) +
            0.15 * abs(gr) / 0.001,
            0.0, 1.0
        )
        # EMA update
        self._vol_ema = 0.90 * float(self._vol_ema) + 0.10 * float(vol_proxy)

        high_vol = self._vol_ema >= float(self.cfg.high_vol_th)
        high_gas = _clip(abs(gr) / 0.001, 0.0, 1.0) >= float(self.cfg.high_gas_th)

        regime = "normal"
        if high_vol and high_gas:
            regime = "high_vol_high_gas"
        elif high_vol:
            regime = "high_vol"
        elif high_gas:
            regime = "high_gas"
        else:
            # opportunity-rich if dex opps high
            if feats.get("dex.opps_per_block", 0.0) > 3.0 and mr > 0.0008:
                regime = "opportunity_rich"

        self._last_regime = regime

        # cluster id in {0..3}
        vol_cluster = 0
        if self._vol_ema > 0.90:
            vol_cluster = 3
        elif self._vol_ema > 0.70:
            vol_cluster = 2
        elif self._vol_ema > 0.40:
            vol_cluster = 1

        emb = _hash_embed(feats, dim=int(self.cfg.dim))

        raw = {
            "bus": snap,
            "local": dict(local_state or {}),
            "vol_ema": float(self._vol_ema),
        }
        # PHASE 9: Market Knowledge Graph update + GraphRAG context
        try:
            # local_state does not yet include S_global; attach minimal for graph update
            _tmp = dict(local_state or {})
            _tmp["S_global"] = {"regime": regime}
            GRAPH.update_from_snapshot(snap=snap, local_state=_tmp, ts=now)
            ctx = RAG.retrieve(g=GRAPH, local_state=_tmp)
            if not isinstance(ctx, dict):
                ctx = _empty_graph_context(
                    degraded=True,
                    error_code="graph_context_invalid",
                    detail=f"non_mapping:{type(ctx).__name__}",
                )
            else:
                ctx = {
                    **_empty_graph_context(degraded=False),
                    **dict(ctx),
                    "degraded": bool(ctx.get("degraded", False)),
                    "error_code": str(ctx.get("error_code", "") or ""),
                    "error": str(ctx.get("error", "") or ""),
                }
        except _SAFE_GRAPH_CONTEXT_EXCEPTIONS as exc:
            ctx = _empty_graph_context(
                degraded=True,
                error_code="graph_context_unavailable",
                detail=repr(exc),
            )
        return GlobalMarketState(ts=float(now), features=feats, regime=str(regime), vol_cluster=int(vol_cluster), embedding=emb, context=ctx, raw=raw)


# Global singleton (safe)
ENGINE = MarketFusionEngine()
