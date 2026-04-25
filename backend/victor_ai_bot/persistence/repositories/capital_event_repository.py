from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List

from ..db import PersistenceDB


class CapitalEventRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)
        self._ensure()

    def _ensure(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS capital_event_bus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_capital_event_bus_chain_domain_ts ON capital_event_bus(chain, domain, ts_ms DESC, id DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_capital_event_bus_chain_source_ts ON capital_event_bus(chain, source, ts_ms DESC, id DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_capital_event_bus_chain_receipt ON capital_event_bus(chain, receipt_id, ts_ms DESC, id DESC)"
            )

    def append_event(
        self,
        *,
        ts_ms: int,
        domain: str,
        event_type: str,
        source: str,
        payload: Dict[str, Any],
        transaction_id: str = "",
        receipt_id: str = "",
        entity_id: str = "",
        conn: sqlite3.Connection | None = None,
    ) -> None:
        event_payload = {
            "ts_ms": int(ts_ms or 0),
            "domain": str(domain or "unknown"),
            "event_type": str(event_type or "unknown"),
            "source": str(source or "unknown"),
            "transaction_id": str(transaction_id or ""),
            "receipt_id": str(receipt_id or ""),
            "entity_id": str(entity_id or ""),
            "payload": dict(payload or {}),
        }
        params = (
            self.chain,
            int(ts_ms or 0),
            str(domain or "unknown"),
            str(event_type or "unknown"),
            str(source or "unknown"),
            str(transaction_id or ""),
            str(receipt_id or ""),
            str(entity_id or ""),
            json.dumps(event_payload, sort_keys=True),
        )
        if conn is not None:
            conn.execute(
                "INSERT INTO capital_event_bus(chain, ts_ms, domain, event_type, source, transaction_id, receipt_id, entity_id, payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
                params,
            )
            return
        with self.db.connect() as owned_conn:
            owned_conn.execute(
                "INSERT INTO capital_event_bus(chain, ts_ms, domain, event_type, source, transaction_id, receipt_id, entity_id, payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
                params,
            )

    def latest_event(
        self, *, domain: str | None = None, event_type: str | None = None, source: str | None = None
    ) -> Dict[str, Any]:
        clauses = ["chain=?"]
        params: list[Any] = [self.chain]
        if domain:
            clauses.append("domain=?")
            params.append(str(domain))
        if event_type:
            clauses.append("event_type=?")
            params.append(str(event_type))
        if source:
            clauses.append("source=?")
            params.append(str(source))
        query = (
            "SELECT payload_json FROM capital_event_bus WHERE "
            + " AND ".join(clauses)
            + " ORDER BY ts_ms DESC, id DESC LIMIT 1"
        )
        with self.db.connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        if not row:
            return {}
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return {}
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def tail(self, *, domain: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
        clauses = ["chain=?"]
        params: list[Any] = [self.chain]
        if domain:
            clauses.append("domain=?")
            params.append(str(domain))
        query = (
            "SELECT payload_json FROM capital_event_bus WHERE "
            + " AND ".join(clauses)
            + " ORDER BY ts_ms DESC, id DESC LIMIT ?"
        )
        params.append(int(limit))
        with self.db.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                out.append(dict(payload))
        return out
