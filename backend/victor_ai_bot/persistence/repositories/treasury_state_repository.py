from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List

from ..db import PersistenceDB


class TreasuryStateRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)
        self._ensure()

    def _ensure(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS treasury_state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    state_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_treasury_state_chain_type_ts ON treasury_state_history(chain, state_type, ts_ms DESC, id DESC)"
            )

    def append_snapshot(
        self,
        *,
        ts_ms: int,
        state_type: str,
        payload: Dict[str, Any],
        conn: sqlite3.Connection | None = None,
    ) -> None:
        snapshot_payload = {
            "ts_ms": int(ts_ms or 0),
            "state_type": str(state_type or "capital_snapshot"),
            "payload": dict(payload or {}),
        }
        params = (
            self.chain,
            int(ts_ms or 0),
            str(state_type or "capital_snapshot"),
            json.dumps(snapshot_payload, sort_keys=True),
        )
        if conn is not None:
            conn.execute(
                "INSERT INTO treasury_state_history(chain, ts_ms, state_type, payload_json) VALUES(?,?,?,?)",
                params,
            )
            return
        with self.db.connect() as owned_conn:
            owned_conn.execute(
                "INSERT INTO treasury_state_history(chain, ts_ms, state_type, payload_json) VALUES(?,?,?,?)",
                params,
            )

    def latest(self, *, state_type: str = "capital_snapshot") -> Dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM treasury_state_history WHERE chain=? AND state_type=? ORDER BY ts_ms DESC, id DESC LIMIT 1",
                (self.chain, str(state_type or "capital_snapshot")),
            ).fetchone()
        if not row:
            return {}
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return {}
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def tail(
        self, *, state_type: str = "capital_snapshot", limit: int = 50
    ) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM treasury_state_history WHERE chain=? AND state_type=? ORDER BY ts_ms DESC, id DESC LIMIT ?",
                (self.chain, str(state_type or "capital_snapshot"), int(limit)),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                out.append(dict(payload))
        return out
