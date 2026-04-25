
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


_SAFE_RAG_ENTRY_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError)
_SAFE_RAG_LOAD_EXCEPTIONS = (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError)
_SAFE_RAG_SAVE_EXCEPTIONS = (OSError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _cos(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        va = float(a[i])
        vb = float(b[i])
        dot += va * vb
        na += va * va
        nb += vb * vb
    denom = (math.sqrt(na) * math.sqrt(nb)) or 1.0
    return float(dot / denom)


@dataclass
class RegimeMemoryItem:
    ts: float
    regime: str
    vol_cluster: int
    s_embed: List[float]
    c_embed: List[float]
    route_id: str = ""
    strategy: str = ""
    ok: bool = True
    r_team: float = 0.0
    r_total: float = 0.0
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("meta") is None:
            d["meta"] = {}
        return d


class RegimeMemoryStore:
    """Persistent store for historical regime embeddings + outcomes.

    CAQ-KDS Layer 3: Retrieval-Augmented Strategy Context.

    Design goals:
      - dependency-free
      - append-only jsonl
      - safe defaults: if file missing/corrupt, system continues
    """

    def __init__(self, *, data_dir: str, name: str = "regime_memory.jsonl", max_items: int = 5000):
        self.data_dir = str(data_dir or "")
        root = self.data_dir or os.path.join(os.getcwd(), "data")
        self.path = os.path.join(root, "caq_kds", name)
        self.max_items = int(max_items)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._cache: List[RegimeMemoryItem] = []
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        items: List[RegimeMemoryItem] = []
        try:
            if not os.path.exists(self.path):
                self._cache = []
                return
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        items.append(
                            RegimeMemoryItem(
                                ts=float(obj.get("ts", 0.0)),
                                regime=str(obj.get("regime", "")),
                                vol_cluster=int(obj.get("vol_cluster", 0) or 0),
                                s_embed=list(obj.get("s_embed") or []),
                                c_embed=list(obj.get("c_embed") or []),
                                route_id=str(obj.get("route_id", "")),
                                strategy=str(obj.get("strategy", "")),
                                ok=bool(obj.get("ok", True)),
                                r_team=float(obj.get("r_team", 0.0) or 0.0),
                                r_total=float(obj.get("r_total", 0.0) or 0.0),
                                meta=dict(obj.get("meta") or {}),
                            )
                        )
                    except _SAFE_RAG_ENTRY_EXCEPTIONS:
                        continue
        except _SAFE_RAG_LOAD_EXCEPTIONS:
            items = []
        # keep newest N
        if len(items) > self.max_items:
            items = items[-self.max_items :]
        self._cache = items

    def append(self, item: RegimeMemoryItem) -> None:
        self._load()
        self._cache.append(item)
        if len(self._cache) > self.max_items:
            self._cache = self._cache[-self.max_items :]
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(item.to_dict(), separators=(",", ":"), ensure_ascii=False) + "\n")
        except _SAFE_RAG_SAVE_EXCEPTIONS:
            pass

    def query(self, *, s_embed: List[float], c_embed: List[float], regime: str = "", k: int = 6) -> List[Tuple[float, RegimeMemoryItem]]:
        self._load()
        scored: List[Tuple[float, RegimeMemoryItem]] = []
        for it in self._cache[-self.max_items :]:
            sim_s = _cos(s_embed, it.s_embed)
            sim_c = _cos(c_embed, it.c_embed)
            sim = 0.70 * sim_s + 0.30 * sim_c
            # Prefer same regime and recent
            if it.regime and regime and it.regime == regime:
                sim += 0.01
            age = max(0.0, time.time() - float(it.ts))
            rec = math.exp(-age / (60.0 * 60.0 * 6.0))  # 6h decay
            sim = float(sim) * (0.7 + 0.3 * rec)
            scored.append((float(sim), it))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[: int(k)]


class RagStrategyContextEngine:
    """Retrieval Augmented Strategy Context.

    Output:
      - Historical_Context dict containing:
          - vector: numeric embedding
          - examples: top-k memory items (redacted + bounded)
          - stats: aggregated outcomes for similar regimes
    """

    def __init__(self, *, data_dir: str):
        self.store = RegimeMemoryStore(data_dir=data_dir)
        self._last_regime: str = ""
        self._last_state: Dict[str, Any] = {}

    def _extract_embeds(self, state: Dict[str, Any]) -> Tuple[List[float], List[float], str, int]:
        S = state.get("S_global") or {}
        if not isinstance(S, dict):
            S = {}
        s_emb = list(S.get("embedding") or [])
        regime = str(S.get("regime") or "")
        vol_cluster = int(S.get("vol_cluster") or 0)
        Ct = state.get("C_t") or {}
        if isinstance(Ct, dict):
            c_emb = list(Ct.get("embedding") or [])
        else:
            c_emb = []
        return s_emb, c_emb, regime, vol_cluster

    def attach_context(self, *, state: Dict[str, Any]) -> Dict[str, Any]:
        """Attach Historical_Context to the mutable state dict."""
        s_emb, c_emb, regime, vol_cluster = self._extract_embeds(state)
        if not s_emb:
            return {}

        scored = self.store.query(s_embed=s_emb, c_embed=c_emb, regime=regime, k=6)

        # aggregate outcomes
        if scored:
            sims = [max(0.0, float(s)) for s, _ in scored]
            wsum = sum(sims) or 1.0
            avg_r = sum(float(it.r_total) * float(s) for s, it in scored) / wsum
            winrate = sum((1.0 if it.ok else 0.0) * float(s) for s, it in scored) / wsum
        else:
            avg_r = 0.0
            winrate = 0.0

        examples = []
        for s, it in scored[:4]:
            ex = {
                "sim": float(round(float(s), 5)),
                "ts": float(it.ts),
                "regime": str(it.regime),
                "vol_cluster": int(it.vol_cluster),
                "ok": bool(it.ok),
                "r_total": float(round(float(it.r_total), 6)),
                "route_id": str(it.route_id)[:80],
                "strategy": str(it.strategy)[:64],
            }
            examples.append(ex)

        hist_vec = [0.0] * (len(s_emb) or 1)
        if scored:
            for sim, it in scored:
                for i, v in enumerate(it.s_embed[: len(hist_vec)]):
                    hist_vec[i] += float(sim) * float(v)
            norm = math.sqrt(sum(x * x for x in hist_vec)) or 1.0
            hist_vec = [float(x / norm) for x in hist_vec]

        out = {
            "avg_r_total": float(avg_r),
            "winrate": float(winrate),
            "examples": examples,
            "vector": hist_vec[:64],
        }
        state["Historical_Context"] = out
        # Keep last state for outcome logging
        self._last_state = dict(state)
        self._last_regime = regime
        return out

    def record_outcome(self, *, route_id: str, strategy: str, ok: bool, r_team: float, r_total: float, meta: Optional[Dict[str, Any]] = None) -> None:
        # Use last observed state embeds
        st = dict(self._last_state or {})
        s_emb, c_emb, regime, vol_cluster = self._extract_embeds(st)
        if not s_emb:
            return
        item = RegimeMemoryItem(
            ts=float(time.time()),
            regime=str(regime),
            vol_cluster=int(vol_cluster),
            s_embed=list(s_emb[:64]),
            c_embed=list(c_emb[:48]),
            route_id=str(route_id or ""),
            strategy=str(strategy or ""),
            ok=bool(ok),
            r_team=float(r_team),
            r_total=float(r_total),
            meta=dict(meta or {}),
        )
        self.store.append(item)

