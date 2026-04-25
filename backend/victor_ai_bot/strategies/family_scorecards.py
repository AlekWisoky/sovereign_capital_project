from __future__ import annotations

import json
import os
from json import JSONDecodeError
from typing import Any, Dict

from ..persistence.db import PersistenceDB
from ..persistence.repositories.scorecard_repo import FamilyScorecardRepository


class FamilyScorecardStore:
    def __init__(self, path: str, *, chain: str = "default"):
        self.path = path
        self.chain = str(chain)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._state = self._load()
        self._db = PersistenceDB(
            os.path.join(
                os.path.dirname(os.path.dirname(path)), "state", "xdv_runtime_state.sqlite3"
            )
        )
        self._repo = FamilyScorecardRepository(self._db, chain=self.chain)

    def _blank(self) -> Dict[str, Any]:
        return {}

    def _coerce_regimes(self, data: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(data, dict):
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for regime, state in data.items():
            if not isinstance(state, dict):
                continue
            out[str(regime)] = {
                "count": int(state.get("count") or 0),
                "pnlUsd": float(state.get("pnlUsd") or 0.0),
                "successes": int(state.get("successes") or 0),
                "gasUsd": float(state.get("gasUsd") or 0.0),
            }
        return out

    def _coerce_family_state(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        return {
            "count": int(data.get("count") or 0),
            "realizedPnlUsd": float(data.get("realizedPnlUsd") or 0.0),
            "gasCostUsd": float(data.get("gasCostUsd") or 0.0),
            "successes": int(data.get("successes") or 0),
            "drawdownPenalty": float(data.get("drawdownPenalty") or 0.0),
            "correlationPenalty": float(data.get("correlationPenalty") or 0.0),
            "regimes": self._coerce_regimes(data.get("regimes") or {}),
        }

    def _coerce_state(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return self._blank()
        out: Dict[str, Any] = {}
        for family, state in data.items():
            fam = str(family or "")
            if not fam:
                continue
            out[fam] = self._coerce_family_state(state)
        return out

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return self._coerce_state(data)
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def observe(
        self,
        *,
        family: str,
        realized_pnl_usd: float,
        gas_cost_usd: float,
        ok: bool,
        regime: str,
        correlation_penalty: float = 0.0,
    ) -> None:
        fam = str(family or "flashloan_atomic")
        s = dict(self._state.get(fam) or {})
        s["count"] = int(s.get("count") or 0) + 1
        s["realizedPnlUsd"] = float(s.get("realizedPnlUsd") or 0.0) + float(realized_pnl_usd)
        s["gasCostUsd"] = float(s.get("gasCostUsd") or 0.0) + float(gas_cost_usd)
        s["successes"] = int(s.get("successes") or 0) + (1 if ok else 0)
        s["drawdownPenalty"] = float(s.get("drawdownPenalty") or 0.0) + (
            0.0 if ok else max(0.0, float(gas_cost_usd))
        )
        s["correlationPenalty"] = float(s.get("correlationPenalty") or 0.0) + float(
            correlation_penalty
        )
        regimes = dict(s.get("regimes") or {})
        rk = str(regime or "unknown")
        r = dict(regimes.get(rk) or {})
        r["count"] = int(r.get("count") or 0) + 1
        r["pnlUsd"] = float(r.get("pnlUsd") or 0.0) + float(realized_pnl_usd)
        r["successes"] = int(r.get("successes") or 0) + (1 if ok else 0)
        r["gasUsd"] = float(r.get("gasUsd") or 0.0) + float(gas_cost_usd)
        regimes[rk] = r
        s["regimes"] = regimes
        self._state[fam] = s
        self._save()
        self._repo.upsert(fam, s)

    def snapshot(self) -> Dict[str, Any]:
        snap = self._repo.snapshot()
        if snap.get("families"):
            return snap
        out = []
        for fam, s in sorted(self._state.items()):
            count = int(s.get("count") or 0)
            realized = float(s.get("realizedPnlUsd") or 0.0)
            gas = float(s.get("gasCostUsd") or 0.0)
            out.append(
                {
                    "family": fam,
                    "count": count,
                    "realizedPnlUsd": round(realized, 6),
                    "stability": round((int(s.get("successes") or 0) / max(1, count)), 6),
                    "drawdownPenaltyUsd": round(float(s.get("drawdownPenalty") or 0.0), 6),
                    "gasEfficiency": round(realized / max(1.0, gas), 6),
                    "executionSuccessRate": round(
                        (int(s.get("successes") or 0) / max(1, count)), 6
                    ),
                    "regimeDependence": {
                        k: int((v or {}).get("count") or 0) if isinstance(v, dict) else int(v or 0)
                        for k, v in dict(s.get("regimes") or {}).items()
                    },
                    "regimePerformance": {
                        k: {
                            "count": int((v or {}).get("count") or 0),
                            "pnlUsd": round(float((v or {}).get("pnlUsd") or 0.0), 6),
                            "successRate": round(
                                float((v or {}).get("successes") or 0)
                                / max(1, int((v or {}).get("count") or 0)),
                                6,
                            ),
                            "gasEfficiency": round(
                                float((v or {}).get("pnlUsd") or 0.0)
                                / max(1.0, float((v or {}).get("gasUsd") or 0.0)),
                                6,
                            ),
                        }
                        for k, v in dict(s.get("regimes") or {}).items()
                        if isinstance(v, dict)
                    },
                    "correlationPenalty": round(float(s.get("correlationPenalty") or 0.0), 6),
                }
            )
        return {"families": out}
