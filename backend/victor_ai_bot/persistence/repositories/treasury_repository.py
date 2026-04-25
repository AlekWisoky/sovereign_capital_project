from __future__ import annotations

import json
from typing import Any, Dict, List

from ..db import PersistenceDB


class TreasuryMetricsRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    def insert_snapshot(self, *, ts_ms: int, metrics: Dict[str, Any]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO treasury_metrics(chain, ts_ms, utilization_rate, deployed_capital_wei, idle_capital_wei, return_on_deployed, return_on_at_risk, failure_adjusted_efficiency, payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    self.chain,
                    int(ts_ms),
                    float(metrics.get("utilization_rate") or 0.0),
                    int(metrics.get("deployed_capital_wei") or 0),
                    int(metrics.get("idle_capital_wei") or 0),
                    float(metrics.get("return_on_deployed_capital") or 0.0),
                    float(metrics.get("return_on_at_risk_capital") or 0.0),
                    float(metrics.get("failure_adjusted_efficiency") or 0.0),
                    json.dumps(metrics, sort_keys=True),
                ),
            )

    def latest(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT ts_ms, payload_json FROM treasury_metrics WHERE chain = ? ORDER BY ts_ms DESC LIMIT ?",
                (self.chain, int(limit)),
            ).fetchall()
        return [json.loads(r["payload_json"]) | {"ts_ms": int(r["ts_ms"])} for r in rows]
