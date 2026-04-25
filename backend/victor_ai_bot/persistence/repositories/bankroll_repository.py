from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List

from ..db import PersistenceDB


class BankrollEventRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)
        self._ensure()

    def _ensure(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bankroll_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    realized_profit_wei INTEGER NOT NULL,
                    last_amount_in_wei INTEGER NOT NULL,
                    success_streak INTEGER NOT NULL,
                    fail_streak INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bankroll_events_chain_ts ON bankroll_events(chain, ts_ms DESC, id DESC)"
            )

    def append_event(
        self,
        *,
        ts_ms: int,
        event_type: str,
        state: Dict[str, Any],
        payload: Dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        state_payload = dict(state or {})
        event_payload = {
            "ts_ms": int(ts_ms or 0),
            "event_type": str(event_type or "unknown"),
            "state": state_payload,
            "payload": dict(payload or {}),
        }
        params = (
            self.chain,
            int(ts_ms or 0),
            str(event_type or "unknown"),
            int(state_payload.get("realized_profit_wei") or 0),
            int(state_payload.get("last_amount_in_wei") or 0),
            int(state_payload.get("success_streak") or 0),
            int(state_payload.get("fail_streak") or 0),
            json.dumps(event_payload, sort_keys=True),
        )
        if conn is not None:
            conn.execute(
                "INSERT INTO bankroll_events(chain, ts_ms, event_type, realized_profit_wei, last_amount_in_wei, success_streak, fail_streak, payload_json) VALUES(?,?,?,?,?,?,?,?)",
                params,
            )
            return
        with self.db.connect() as owned_conn:
            owned_conn.execute(
                "INSERT INTO bankroll_events(chain, ts_ms, event_type, realized_profit_wei, last_amount_in_wei, success_streak, fail_streak, payload_json) VALUES(?,?,?,?,?,?,?,?)",
                params,
            )

    def latest_event(self) -> Dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM bankroll_events WHERE chain=? ORDER BY ts_ms DESC, id DESC LIMIT 1",
                (self.chain,),
            ).fetchone()
        if not row:
            return {}
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return {}
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def tail(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM bankroll_events WHERE chain=? ORDER BY ts_ms DESC, id DESC LIMIT ?",
                (self.chain, int(limit)),
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
