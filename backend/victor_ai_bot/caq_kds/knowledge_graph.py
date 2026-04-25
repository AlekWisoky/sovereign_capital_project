from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


_SAFE_ATTR_EXCEPTIONS = (TypeError, ValueError)
_SAFE_STATE_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def _stable_hash(s: str) -> int:
    h = hashlib.blake2b(s.encode("utf-8", errors="ignore"), digest_size=8).digest()
    return int.from_bytes(h, "little", signed=False)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class Node:
    id: str
    type: str
    attrs: Dict[str, Any] = field(default_factory=dict)
    ts: float = 0.0


@dataclass
class Edge:
    src: str
    dst: str
    rel: str
    weight: float = 0.0
    ts: float = 0.0


class MarketKnowledgeGraph:
    """Dynamic Market Knowledge Graph (MKG) with temporal decay."""

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[Tuple[str, str, str], Edge] = {}
        self.decay_halflife_s: float = 120.0
        self._status: Dict[str, Any] = {
            "update": {"ok": True, "last_error_code": "", "last_error": "", "last_update_ts": 0.0},
            "degraded": False,
        }

    def upsert_node(self, node_id: str, node_type: str, attrs: Optional[Dict[str, Any]] = None, *, ts: Optional[float] = None) -> None:
        now = float(ts if ts is not None else time.time())
        node = self.nodes.get(node_id)
        if node is None:
            node = Node(id=str(node_id), type=str(node_type), attrs={}, ts=now)
        node.type = str(node_type)
        if isinstance(attrs, dict):
            try:
                node.attrs.update(dict(attrs))
            except _SAFE_ATTR_EXCEPTIONS:
                pass
        node.ts = now
        self.nodes[node_id] = node

    def upsert_edge(self, src: str, dst: str, rel: str, weight: float, *, ts: Optional[float] = None) -> None:
        now = float(ts if ts is not None else time.time())
        key = (str(src), str(dst), str(rel))
        edge = self.edges.get(key)
        if edge is None:
            edge = Edge(src=str(src), dst=str(dst), rel=str(rel), weight=float(weight), ts=now)
        edge.weight = float(_clip(0.75 * float(edge.weight) + 0.25 * float(weight), -10.0, 10.0))
        edge.ts = now
        self.edges[key] = edge

    def _record_update_status(self, *, ok: bool, code: str = "", detail: str = "") -> None:
        entry = self._status["update"]
        entry["ok"] = bool(ok)
        entry["last_error_code"] = str(code or "")
        entry["last_error"] = str(detail or "")
        entry["last_update_ts"] = float(time.time())
        self._status["degraded"] = not bool(entry.get("ok", True))

    def state(self) -> Dict[str, Any]:
        return {
            "node_count": int(len(self.nodes)),
            "edge_count": int(len(self.edges)),
            "update": dict(self._status["update"]),
            "degraded": bool(self._status["degraded"]),
        }

    def decay(self, *, now: Optional[float] = None) -> None:
        t = float(now if now is not None else time.time())
        hl = max(5.0, float(self.decay_halflife_s))
        lam = math.log(2.0) / hl
        to_delete = []
        for key, edge in self.edges.items():
            age = max(0.0, t - float(edge.ts))
            edge.weight *= math.exp(-lam * age)
            if abs(edge.weight) < 1e-4:
                to_delete.append(key)
        for key in to_delete:
            self.edges.pop(key, None)

    def update_from_snapshot(self, *, snap: Dict[str, Any], local_state: Dict[str, Any], ts: Optional[float] = None) -> None:
        now = float(ts if ts is not None else time.time())
        self.decay(now=now)

        S = local_state.get("S_global") or {}
        regime = str(S.get("regime", "unknown") or "unknown") if isinstance(S, dict) else "unknown"
        self.upsert_node(f"regime:{regime}", "regime", {"name": regime}, ts=now)

        try:
            cex = (snap.get("cex") or {}).get("data") or {}
            if isinstance(cex, dict):
                self.upsert_node("venue:cex", "venue", {"kind": "cex"}, ts=now)
                self.upsert_edge(f"regime:{regime}", "venue:cex", "influences", float(cex.get("funding_change_bps", 0.0) or 0.0) / 10.0, ts=now)

            dex = (snap.get("dex") or {}).get("data") or {}
            if isinstance(dex, dict):
                self.upsert_node("venue:dex", "venue", {"kind": "dex"}, ts=now)
                self.upsert_edge(f"regime:{regime}", "venue:dex", "influences", float(dex.get("opps_per_block", 0.0) or 0.0) / 5.0, ts=now)

            mev = (snap.get("mev") or {}).get("data") or {}
            if isinstance(mev, dict):
                self.upsert_node("stream:mev", "stream", {"kind": "mempool"}, ts=now)
                self.upsert_edge(f"regime:{regime}", "stream:mev", "influences", float(mev.get("sandwich_risk", 0.0) or 0.0), ts=now)

            mr = float(local_state.get("margin_ratio", 0.0) or 0.0)
            legs = int(local_state.get("legs", 2) or 2)
            self.upsert_node("metric:margin", "metric", {"mr": mr}, ts=now)
            self.upsert_node("metric:legs", "metric", {"legs": legs}, ts=now)
            self.upsert_edge("metric:margin", f"regime:{regime}", "correlates", mr / 0.001, ts=now)
        except _SAFE_STATE_EXCEPTIONS as exc:
            self._record_update_status(ok=False, code="graph_update_failed", detail=repr(exc))
            return
        self._record_update_status(ok=True)


class GraphRAG:
    """Retrieve subgraphs relevant to the current state and produce C_t."""

    def __init__(self, *, dim: int = 48):
        self.dim = int(dim)

    def _hash_embed(self, items: List[Tuple[str, float]]) -> List[float]:
        vec = [0.0] * self.dim
        for key, value in items:
            idx = _stable_hash(key) % self.dim
            vec[idx] += float(value)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [float(x / norm) for x in vec]

    def retrieve(self, *, g: MarketKnowledgeGraph, local_state: Dict[str, Any]) -> Dict[str, Any]:
        anchors = []
        S = local_state.get("S_global") or {}
        if isinstance(S, dict):
            anchors.append(f"regime:{S.get('regime', 'unknown')}")
        anchors.extend(["venue:dex", "venue:cex", "stream:mev"])

        items: List[Tuple[str, float]] = []
        edges: List[Dict[str, Any]] = []
        for (src, dst, rel), edge in list(g.edges.items()):
            if src in anchors or dst in anchors:
                items.append((f"{src}|{rel}|{dst}", float(edge.weight)))
                edges.append({"src": src, "dst": dst, "rel": rel, "w": float(edge.weight), "ts": float(edge.ts)})
        emb = self._hash_embed(items)
        novelty = _clip(len(edges) / 15.0, 0.0, 1.0)
        return {
            "anchors": anchors,
            "edge_count": int(len(edges)),
            "edges": edges[:50],
            "embedding": emb,
            "novelty": float(novelty),
        }


GRAPH = MarketKnowledgeGraph()
RAG = GraphRAG()
