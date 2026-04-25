from __future__ import annotations

import json
from typing import Any, Dict, List

from ..db import PersistenceDB


class LifecycleHistoryRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    def append(
        self,
        *,
        ts_ms: int,
        family: str,
        strategy_id: str,
        stage: str,
        reason_code: str,
        payload: Dict[str, Any],
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO lifecycle_history(chain, ts_ms, family, strategy_id, stage, reason_code, payload_json) VALUES(?,?,?,?,?,?,?)",
                (
                    self.chain,
                    int(ts_ms),
                    str(family),
                    str(strategy_id),
                    str(stage),
                    str(reason_code),
                    json.dumps(payload or {}, sort_keys=True),
                ),
            )

    def query(self, *, family: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        sql = "SELECT ts_ms,family,strategy_id,stage,reason_code,payload_json FROM lifecycle_history WHERE chain = ?"
        params: List[Any] = [self.chain]
        if family:
            sql += " AND family = ?"
            params.append(str(family))
        sql += " ORDER BY ts_ms DESC LIMIT ?"
        params.append(int(limit))
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload_json"] or "{}")} for r in rows]
