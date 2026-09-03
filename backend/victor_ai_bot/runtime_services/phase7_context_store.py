from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict


class Phase7ContextStore:
    """Small append-only context journal keyed by transaction hash.

    It carries decision-time context, not financial authority. The store is
    deliberately separate from submission so a slow disk write cannot delay
    transaction delivery. Reads are cached in-process for settlement/learning.
    """

    def __init__(self, *, data_dir: str, chain: str):
        root = str(data_dir or "backend/data")
        self.chain = str(chain or "default")
        self.path = os.path.join(root, "phase7", f"context_{self.chain}.jsonl")
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _key(tx_hash: Any) -> str:
        return str(tx_hash or "").strip().lower()

    def put(self, tx_hash: str, context: Dict[str, Any]) -> bool:
        key = self._key(tx_hash)
        if not key:
            return False
        row = {"tx_hash": key, "context": dict(context or {})}
        with self._lock:
            self._cache[key] = dict(row["context"])
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                return True
            except (OSError, TypeError, ValueError):
                return False

    def get(self, tx_hash: str) -> Dict[str, Any]:
        key = self._key(tx_hash)
        if not key:
            return {}
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return dict(cached)
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            row = json.loads(line)
                        except (TypeError, ValueError):
                            continue
                        if not isinstance(row, dict) or self._key(row.get("tx_hash")) != key:
                            continue
                        context = row.get("context")
                        if isinstance(context, dict):
                            self._cache[key] = dict(context)
                            return dict(context)
            except OSError:
                return {}
        return {}

    def state(self) -> Dict[str, Any]:
        return {
            "chain": self.chain,
            "path": self.path,
            "cachedCount": len(self._cache),
        }


def phase7_context_store(runtime: Any) -> Phase7ContextStore:
    existing = getattr(runtime, "_phase7_context_store", None)
    if isinstance(existing, Phase7ContextStore):
        return existing
    cfg = getattr(runtime, "cfg", None)
    chain = getattr(getattr(cfg, "chain", None), "name", "default") or "default"
    data_dir = getattr(runtime, "data_dir", None) or os.path.join("backend", "data")
    store = Phase7ContextStore(data_dir=str(data_dir), chain=str(chain))
    try:
        setattr(runtime, "_phase7_context_store", store)
    except (AttributeError, TypeError):
        pass
    return store
