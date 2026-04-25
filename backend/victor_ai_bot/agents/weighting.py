from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Dict, List

_SAFE_WEIGHT_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)

from .contracts import canonical_agent_name
from .regime_policy import regime_weights


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class AgentWeightingGovernor:
    path: str

    def __post_init__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._state = self._load()

    def _blank(self) -> Dict[str, Any]:
        return {"metrics": {}}

    def _coerce_metric(self, raw: Any) -> Dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        try:
            count = max(0, int(raw.get("count") or 0))
            precision_hits = max(0, int(raw.get("precision_hits") or 0))
            followed = max(0, int(raw.get("followed") or 0))
            realized_edge_usd = float(raw.get("realized_edge_usd") or 0.0)
        except (TypeError, ValueError):
            return None
        return {
            "count": count,
            "precision_hits": min(precision_hits, count),
            "followed": min(followed, count),
            "realized_edge_usd": realized_edge_usd,
        }

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except _SAFE_WEIGHT_LOAD_EXCEPTIONS:
            return self._blank()
        if not isinstance(data, dict):
            return self._blank()
        metrics = data.get("metrics")
        if not isinstance(metrics, dict):
            return self._blank()
        out: Dict[str, Any] = self._blank()
        for key, raw in metrics.items():
            metric = self._coerce_metric(raw)
            if metric is None:
                continue
            out["metrics"][str(key)] = metric
        return out

    def _save(self) -> None:
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def observe(self, *, agent: str, regime: str, followed: bool, predicted_signal: float, realized_edge_usd: float) -> None:
        agent_key = canonical_agent_name(agent)
        key = f"{agent_key}|{regime}"
        m = dict((self._state.get('metrics') or {}).get(key) or {})
        count = int(m.get('count') or 0) + 1
        precision_hits = int(m.get('precision_hits') or 0)
        if (predicted_signal >= 0 and realized_edge_usd >= 0) or (predicted_signal < 0 and realized_edge_usd <= 0):
            precision_hits += 1
        m.update({
            'count': count,
            'precision_hits': precision_hits,
            'followed': int(m.get('followed') or 0) + (1 if followed else 0),
            'realized_edge_usd': float(m.get('realized_edge_usd') or 0.0) + float(realized_edge_usd),
        })
        self._state.setdefault('metrics', {})[key] = m
        self._save()

    def weights_for(self, *, regime: str, agents: List[str]) -> Dict[str, float]:
        base = regime_weights(regime)
        out: Dict[str, float] = {}
        for requested in agents:
            agent = canonical_agent_name(requested)
            key = f"{agent}|{regime}"
            m = dict((self._state.get('metrics') or {}).get(key) or {})
            count = int(m.get('count') or 0)
            precision = float(m.get('precision_hits') or 0) / float(max(1, count))
            realized = float(m.get('realized_edge_usd') or 0.0)
            follow_rate = float(m.get('followed') or 0) / float(max(1, count))
            quality = 0.85 + (precision * 0.30) + (_clip(realized / max(1.0, count), -1.0, 1.0) * 0.10) + (follow_rate * 0.05)
            out[requested] = round(_clip(base.get(agent, 1.0) * quality, 0.25, 1.75), 6)
        return out

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._state)
