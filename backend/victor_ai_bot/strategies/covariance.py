from __future__ import annotations

import json
import os
from json import JSONDecodeError
from typing import Any, Dict, List


def _mean(vals: List[float]) -> float:
    return sum(vals) / float(len(vals)) if vals else 0.0


def _cov(xs: List[float], ys: List[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    x = xs[-n:]
    y = ys[-n:]
    mx = _mean(x)
    my = _mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / float(max(1, n - 1))


def _var(xs: List[float]) -> float:
    return _cov(xs, xs)


class FamilyCovarianceStore:
    def __init__(self, path: str, *, max_points: int = 200):
        self.path = path
        self.max_points = int(max_points)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._state = self._load()

    def _blank(self) -> Dict[str, Any]:
        return {"returns": {}}

    def _coerce_returns(self, value: Any) -> Dict[str, List[float]]:
        if not isinstance(value, dict):
            return {}
        out: Dict[str, List[float]] = {}
        for family, raw_series in value.items():
            fam = str(family or "")
            if not fam or not isinstance(raw_series, list):
                continue
            vals: List[float] = []
            for raw in raw_series:
                try:
                    vals.append(float(raw))
                except (TypeError, ValueError):
                    continue
            out[fam] = vals[-self.max_points :]
        return out

    def _coerce_state(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return self._blank()
        return {"returns": self._coerce_returns(data.get("returns"))}

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()
        return self._coerce_state(data)

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def observe(self, family: str, value: float) -> None:
        fam = str(family or "")
        if not fam:
            return
        vals = list((self._state.get("returns") or {}).get(fam, []) or [])
        vals.append(float(value))
        vals = vals[-self.max_points :]
        self._state.setdefault("returns", {})[fam] = vals
        self._save()

    def covariance_matrix(self) -> Dict[str, Dict[str, float]]:
        data = dict(self._state.get("returns") or {})
        fams = sorted(data.keys())
        out: Dict[str, Dict[str, float]] = {f: {} for f in fams}
        for i, fa in enumerate(fams):
            for fb in fams[i:]:
                c = _cov(list(data.get(fa) or []), list(data.get(fb) or []))
                va = _var(list(data.get(fa) or []))
                vb = _var(list(data.get(fb) or []))
                corr = 0.0
                if va > 1e-12 and vb > 1e-12:
                    corr = max(-1.0, min(1.0, c / ((va**0.5) * (vb**0.5))))
                out[fa][fb] = round(corr, 6)
                out.setdefault(fb, {})[fa] = round(corr, 6)
        return out

    def penalties(self) -> Dict[str, float]:
        mat = self.covariance_matrix()
        out: Dict[str, float] = {}
        for fam, row in mat.items():
            vals = [abs(float(v)) for other, v in row.items() if other != fam]
            out[fam] = round(min(0.25, (sum(vals) / float(len(vals)) if vals else 0.0) * 0.25), 6)
        return out
