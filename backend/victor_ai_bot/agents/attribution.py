from __future__ import annotations

import json
import os
from json import JSONDecodeError
from typing import Any, Dict, List

from ..persistence.db import PersistenceDB
from ..persistence.repositories.agent_repo import AgentAttributionRepository


class AgentAttributionStore:
    def __init__(self, path: str, *, max_items: int = 2000, chain: str = 'default'):
        self.path = path
        self.max_items = int(max_items)
        self.chain = str(chain)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._db = PersistenceDB(os.path.join(os.path.dirname(os.path.dirname(path)), 'state', 'xdv_runtime_state.sqlite3'))
        self._repo = AgentAttributionRepository(self._db, chain=self.chain)

    def append(self, row: Dict[str, Any]) -> None:
        items = self.load(limit=self.max_items)
        items.append(dict(row))
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(items[-self.max_items:], f, indent=2, sort_keys=True)
        self._repo.append(dict(row))

    def _blank(self) -> List[Dict[str, Any]]:
        return []

    def _coerce_contributor(self, item: Any) -> Dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        agent = str(item.get('agent') or '').strip()
        if not agent:
            return None
        out: Dict[str, Any] = {'agent': agent}
        out['followed'] = bool(item.get('followed'))
        out['precision_hit'] = bool(item.get('precision_hit'))
        try:
            out['realized_pnl_impact_usd'] = float(item.get('realized_pnl_impact_usd') or 0.0)
        except (TypeError, ValueError):
            out['realized_pnl_impact_usd'] = 0.0
        for key in ('signal', 'confidence'):
            if key in item:
                try:
                    out[key] = float(item.get(key))
                except (TypeError, ValueError):
                    out[key] = 0.0
        features = item.get('features_used')
        if isinstance(features, dict):
            out['features_used'] = dict(features)
        return out

    def _coerce_row(self, item: Any) -> Dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        contributors = item.get('contributors')
        if contributors is None:
            contributors = []
        if not isinstance(contributors, list):
            return None

        out: Dict[str, Any] = {'contributors': []}
        # Preserve the existing attribution record's canonical lineage metadata
        # in the JSON read history. This is projection-only: decision identity,
        # settlement truth, and persistence authority remain elsewhere.
        out.update({
            key: item.get(key)
            for key in (
                'decision_id',
                'correlation_id',
                'execution_id',
                'receipt_id',
                'outcome_id',
                'sizing_id',
                'opportunity_id',
                'route_id',
                'strategy_family',
                'regime',
                'ts_ms',
            )
            if key in item
        })

        for contrib in contributors:
            coerced = self._coerce_contributor(contrib)
            if coerced is not None:
                out['contributors'].append(coerced)
        return out

    def load(self, limit: int = 500) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f) or []
            if not isinstance(data, list):
                return self._blank()
            out: List[Dict[str, Any]] = []
            for item in data:
                coerced = self._coerce_row(item)
                if coerced is not None:
                    out.append(coerced)
            return out[-int(limit):]
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()

    def summary(self) -> Dict[str, Any]:
        snap = self._repo.summary()
        if snap.get('agents'):
            return snap
        stats: Dict[str, Dict[str, float]] = {}
        for row in self.load(limit=self.max_items):
            for contrib in list(row.get('contributors') or []):
                aid = str(contrib.get('agent') or 'unknown')
                s = stats.get(aid) or {'count': 0.0, 'followed': 0.0, 'realized_pnl_impact_usd': 0.0, 'precision_hits': 0.0}
                s['count'] += 1.0
                s['followed'] += 1.0 if bool(contrib.get('followed')) else 0.0
                s['realized_pnl_impact_usd'] += float(contrib.get('realized_pnl_impact_usd') or 0.0)
                s['precision_hits'] += 1.0 if bool(contrib.get('precision_hit')) else 0.0
                stats[aid] = s
        out = []
        for aid, s in stats.items():
            out.append({
                'agent': aid,
                'count': int(s['count']),
                'followRate': round(s['followed'] / max(1.0, s['count']), 6),
                'precision': round(s['precision_hits'] / max(1.0, s['count']), 6),
                'realizedImpactUsd': round(s['realized_pnl_impact_usd'], 6),
            })
        return {'agents': sorted(out, key=lambda x: (-x['realizedImpactUsd'], x['agent']))}
