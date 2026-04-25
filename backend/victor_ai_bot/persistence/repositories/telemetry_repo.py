from __future__ import annotations

import json
from typing import Any, Dict, List

from ..db import PersistenceDB


class TelemetryRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    def insert(self, *, event_type: str, ts_ms: int, payload: Dict[str, Any]) -> None:
        payload = dict(payload or {})
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO telemetry_events(chain,event_type,ts_ms,route_family,strategy_family,regime,lane,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                (
                    self.chain,
                    str(event_type),
                    int(ts_ms),
                    str(payload.get("route_family") or ""),
                    str(payload.get("strategy_family") or ""),
                    str(payload.get("regime") or ""),
                    str(payload.get("lane") or ""),
                    json.dumps(payload, sort_keys=True),
                ),
            )

    def query(
        self,
        *,
        event_type: str = "",
        route_family: str = "",
        strategy_family: str = "",
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT chain,event_type,ts_ms,payload_json FROM telemetry_events WHERE chain = ?"
        params: List[Any] = [self.chain]
        if event_type:
            sql += " AND event_type = ?"
            params.append(str(event_type))
        if route_family:
            sql += " AND route_family = ?"
            params.append(str(route_family))
        if strategy_family:
            sql += " AND strategy_family = ?"
            params.append(str(strategy_family))
        sql += " ORDER BY ts_ms DESC LIMIT ?"
        params.append(int(limit))
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            out.append(
                {
                    "chain": row["chain"],
                    "event_type": row["event_type"],
                    "ts_ms": row["ts_ms"],
                    "payload": payload,
                }
            )
        return list(reversed(out))
