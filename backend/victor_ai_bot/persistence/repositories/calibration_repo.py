from __future__ import annotations

from typing import Any, Dict, List

from ..db import PersistenceDB


class CalibrationRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    def upsert_observation(
        self,
        *,
        route_family: str,
        lane: str,
        regime: str,
        projected_realized_edge_usd: float,
        actual_realized_edge_usd: float,
        predicted_success_probability: float,
        actual_success: bool,
        predicted_slippage_usd: float,
        actual_slippage_usd: float,
        predicted_interference_probability: float,
        actual_stale: bool,
    ) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_calibration WHERE chain=? AND route_family=? AND lane=? AND regime=?",
                (self.chain, str(route_family), str(lane), str(regime or "")),
            ).fetchone()
            s = (
                dict(row)
                if row is not None
                else {
                    "count": 0,
                    "projected_realized_edge_usd": 0.0,
                    "actual_realized_edge_usd": 0.0,
                    "predicted_success_probability": 0.0,
                    "actual_successes": 0,
                    "predicted_slippage_usd": 0.0,
                    "actual_slippage_usd": 0.0,
                    "predicted_interference_probability": 0.0,
                    "actual_stales": 0,
                }
            )
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
            s["actual_successes"] = int(s.get("actual_successes") or 0) + (
                1 if actual_success else 0
            )
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
            conn.execute(
                "INSERT OR REPLACE INTO execution_calibration(chain,route_family,lane,regime,count,projected_realized_edge_usd,actual_realized_edge_usd,predicted_success_probability,actual_successes,predicted_slippage_usd,actual_slippage_usd,predicted_interference_probability,actual_stales) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    self.chain,
                    str(route_family),
                    str(lane),
                    str(regime or ""),
                    int(s["count"]),
                    float(s["projected_realized_edge_usd"]),
                    float(s["actual_realized_edge_usd"]),
                    float(s["predicted_success_probability"]),
                    int(s["actual_successes"]),
                    float(s["predicted_slippage_usd"]),
                    float(s["actual_slippage_usd"]),
                    float(s["predicted_interference_probability"]),
                    int(s["actual_stales"]),
                ),
            )

    def rows(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            raw = conn.execute(
                "SELECT * FROM execution_calibration WHERE chain = ? ORDER BY route_family, lane, regime",
                (self.chain,),
            ).fetchall()
        return [dict(r) for r in raw]

    def upsert_edge_metrics(
        self,
        *,
        route_family: str,
        lane: str,
        regime: str,
        projected_gross_edge_usd: float,
        projected_realized_edge_usd: float,
        actual_realized_edge_usd: float,
    ) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_edge_metrics WHERE chain=? AND route_family=? AND lane=? AND regime=?",
                (self.chain, str(route_family), str(lane), str(regime or "")),
            ).fetchone()
            s = (
                dict(row)
                if row is not None
                else {
                    "count": 0,
                    "projected_gross_edge_usd": 0.0,
                    "projected_realized_edge_usd": 0.0,
                    "actual_realized_edge_usd": 0.0,
                }
            )
            s["count"] = int(s.get("count") or 0) + 1
            s["projected_gross_edge_usd"] = float(s.get("projected_gross_edge_usd") or 0.0) + float(
                projected_gross_edge_usd
            )
            s["projected_realized_edge_usd"] = float(
                s.get("projected_realized_edge_usd") or 0.0
            ) + float(projected_realized_edge_usd)
            s["actual_realized_edge_usd"] = float(s.get("actual_realized_edge_usd") or 0.0) + float(
                actual_realized_edge_usd
            )
            conn.execute(
                "INSERT OR REPLACE INTO execution_edge_metrics(chain,route_family,lane,regime,count,projected_gross_edge_usd,projected_realized_edge_usd,actual_realized_edge_usd) VALUES(?,?,?,?,?,?,?,?)",
                (
                    self.chain,
                    str(route_family),
                    str(lane),
                    str(regime or ""),
                    int(s["count"]),
                    float(s["projected_gross_edge_usd"]),
                    float(s["projected_realized_edge_usd"]),
                    float(s["actual_realized_edge_usd"]),
                ),
            )

    def edge_rows(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            raw = conn.execute(
                "SELECT * FROM execution_edge_metrics WHERE chain = ? ORDER BY route_family, lane, regime",
                (self.chain,),
            ).fetchall()
        return [dict(r) for r in raw]
