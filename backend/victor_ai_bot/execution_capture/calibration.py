from __future__ import annotations

import json
import os
from typing import Any, Dict

from ..persistence.db import PersistenceDB
from ..persistence.repositories.calibration_repo import CalibrationRepository


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class EmpiricalCalibrationStore:
    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(data_dir, "execution_capture", f"calibration_{chain}.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._state = self._load()
        self._db = PersistenceDB(os.path.join(data_dir, "state", "xdv_runtime_state.sqlite3"))
        self._repo = CalibrationRepository(self._db, chain=chain)

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {}

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def observe(
        self,
        *,
        route_family: str,
        lane: str,
        projected_realized_edge_usd: float,
        actual_realized_edge_usd: float,
        predicted_success_probability: float,
        actual_success: bool,
        predicted_slippage_usd: float,
        actual_slippage_usd: float,
        predicted_interference_probability: float,
        actual_stale: bool,
        regime: str = "",
        projected_gross_edge_usd: float | None = None,
    ) -> None:
        key = f"{route_family}|{lane}"
        s = dict(self._state.get(key) or {})
        s["count"] = int(s.get("count") or 0) + 1
        s["projected_realized_edge_usd"] = float(
            s.get("projected_realized_edge_usd") or 0.0
        ) + float(projected_realized_edge_usd)
        s["actual_realized_edge_usd"] = float(s.get("actual_realized_edge_usd") or 0.0) + float(
            actual_realized_edge_usd
        )
        s["predicted_success_probability"] = float(
            s.get("predicted_success_probability") or 0.0
        ) + float(predicted_success_probability)
        s["actual_successes"] = int(s.get("actual_successes") or 0) + (1 if actual_success else 0)
        s["predicted_slippage_usd"] = float(s.get("predicted_slippage_usd") or 0.0) + float(
            predicted_slippage_usd
        )
        s["actual_slippage_usd"] = float(s.get("actual_slippage_usd") or 0.0) + float(
            actual_slippage_usd
        )
        s["predicted_interference_probability"] = float(
            s.get("predicted_interference_probability") or 0.0
        ) + float(predicted_interference_probability)
        s["actual_stales"] = int(s.get("actual_stales") or 0) + (1 if actual_stale else 0)
        self._state[key] = s
        self._save()
        self._repo.upsert_observation(
            route_family=route_family,
            lane=lane,
            regime=regime,
            projected_realized_edge_usd=projected_realized_edge_usd,
            actual_realized_edge_usd=actual_realized_edge_usd,
            predicted_success_probability=predicted_success_probability,
            actual_success=actual_success,
            predicted_slippage_usd=predicted_slippage_usd,
            actual_slippage_usd=actual_slippage_usd,
            predicted_interference_probability=predicted_interference_probability,
            actual_stale=actual_stale,
        )
        self._repo.upsert_edge_metrics(
            route_family=route_family,
            lane=lane,
            regime=regime,
            projected_gross_edge_usd=float(
                projected_gross_edge_usd
                if projected_gross_edge_usd is not None
                else projected_realized_edge_usd
            ),
            projected_realized_edge_usd=projected_realized_edge_usd,
            actual_realized_edge_usd=actual_realized_edge_usd,
        )

    def priors(self, *, route_family: str, lane: str, regime: str = "") -> Dict[str, float]:
        if hasattr(self, "_repo"):
            rows = [
                r
                for r in self._repo.rows()
                if str(r.get("route_family") or "") == str(route_family)
                and str(r.get("lane") or "") == str(lane)
            ]
            if regime:
                rows = [r for r in rows if str(r.get("regime") or "") == str(regime)] or rows
            if rows:
                s = rows[0]
                count = max(1, int(s.get("count") or 0))
                projected = float(s.get("projected_realized_edge_usd") or 0.0)
                actual = float(s.get("actual_realized_edge_usd") or 0.0)
                predicted_success = float(s.get("predicted_success_probability") or 0.0) / count
                actual_success = float(s.get("actual_successes") or 0) / count
                pred_slip = float(s.get("predicted_slippage_usd") or 0.0) / count
                actual_slip = float(s.get("actual_slippage_usd") or 0.0) / count
                pred_intf = float(s.get("predicted_interference_probability") or 0.0) / count
                actual_stale = float(s.get("actual_stales") or 0) / count
                realization_ratio = actual / projected if projected > 0 else 1.0
                edge_rows = [
                    r
                    for r in self._repo.edge_rows()
                    if str(r.get("route_family") or "") == str(route_family)
                    and str(r.get("lane") or "") == str(lane)
                ]
                if regime:
                    edge_rows = [
                        r for r in edge_rows if str(r.get("regime") or "") == str(regime)
                    ] or edge_rows
                eg = float(
                    (edge_rows[0].get("projected_gross_edge_usd") if edge_rows else projected)
                    or projected
                )
                return {
                    "realization_ratio": realization_ratio,
                    "success_calibration_error": actual_success - predicted_success,
                    "slippage_calibration_error_usd": actual_slip - pred_slip,
                    "interference_calibration_error": actual_stale - pred_intf,
                    "projected_gross_edge_usd": eg / count,
                    "projected_realized_edge_usd": projected / count,
                    "actual_realized_edge_usd": actual / count,
                    "calibration_factor": realization_ratio,
                }
        key = f"{route_family}|{lane}"
        s = dict(self._state.get(key) or {})
        count = max(1, int(s.get("count") or 0))
        projected = float(s.get("projected_realized_edge_usd") or 0.0)
        actual = float(s.get("actual_realized_edge_usd") or 0.0)
        predicted_success = float(s.get("predicted_success_probability") or 0.0) / count
        actual_success = float(s.get("actual_successes") or 0) / count
        pred_slip = float(s.get("predicted_slippage_usd") or 0.0) / count
        actual_slip = float(s.get("actual_slippage_usd") or 0.0) / count
        pred_intf = float(s.get("predicted_interference_probability") or 0.0) / count
        actual_stale = float(s.get("actual_stales") or 0) / count
        realization_ratio = actual / projected if projected > 0 else 1.0
        return {
            "realization_ratio": realization_ratio,
            "success_calibration_error": actual_success - predicted_success,
            "slippage_calibration_error_usd": actual_slip - pred_slip,
            "interference_calibration_error": actual_stale - pred_intf,
            "projected_gross_edge_usd": projected / count,
            "projected_realized_edge_usd": projected / count,
            "actual_realized_edge_usd": actual / count,
            "calibration_factor": realization_ratio,
        }

    def snapshot(self) -> Dict[str, Any]:
        out = []
        seen = set()
        if hasattr(self, "_repo"):
            for row in self._repo.rows():
                route_family = str(row.get("route_family") or "")
                lane = str(row.get("lane") or "")
                regime = str(row.get("regime") or "")
                pri = self.priors(route_family=route_family, lane=lane, regime=regime)
                out.append(
                    {
                        "route_family": route_family,
                        "lane": lane,
                        "regime": regime,
                        **{k: round(float(v), 6) for k, v in pri.items()},
                    }
                )
                seen.add((route_family, lane))
        for key in sorted(self._state.keys()):
            route_family, lane = key.split("|", 1)
            if (route_family, lane) in seen:
                continue
            pri = self.priors(route_family=route_family, lane=lane)
            out.append(
                {
                    "route_family": route_family,
                    "lane": lane,
                    **{k: round(float(v), 6) for k, v in pri.items()},
                }
            )
        return {"items": out}
