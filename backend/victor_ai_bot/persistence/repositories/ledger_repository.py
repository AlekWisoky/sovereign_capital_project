from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, Iterable, List

from ..db import PersistenceDB
from .capital_event_repository import CapitalEventRepository
from ...treasury.ledger import TreasuryLedger


class LedgerRepository:
    def __init__(
        self,
        db: PersistenceDB,
        *,
        capital_event_repo: CapitalEventRepository | None = None,
        chain: str = "",
    ):
        self.db = db
        self._capital_event_repo = capital_event_repo
        self._default_chain = str(chain or "")
        self._ensure()

    def set_capital_event_repo(
        self, repo: CapitalEventRepository | None, *, chain: str | None = None
    ) -> None:
        self._capital_event_repo = repo
        if chain is not None:
            self._default_chain = str(chain or "")

    def _ensure(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS treasury_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                ts_ms INTEGER NOT NULL,
                entry_type TEXT NOT NULL,
                asset TEXT NOT NULL,
                amount REAL NOT NULL,
                venue TEXT,
                family TEXT,
                note TEXT,
                transaction_id TEXT,
                receipt_id TEXT,
                payload_json TEXT NOT NULL
            )
            """
            )
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS treasury_ledger_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                ts_ms INTEGER NOT NULL,
                tx_type TEXT NOT NULL,
                receipt_id TEXT,
                payload_json TEXT NOT NULL
            )
            """
            )

    @staticmethod
    def _aggregate_transaction_balances(rows: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for row in rows:
            for line in list((row or {}).get("lines") or []):
                if not isinstance(line, dict):
                    continue
                account = str(line.get("account") or "")
                asset = str(line.get("asset") or "")
                if not asset or account.startswith("equity:"):
                    continue
                out[asset] = float(out.get(asset, 0.0)) + float(line.get("amount") or 0.0)
        return {k: round(v, 8) for k, v in out.items()}

    def _all_transactions(self, *, chain: str) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM treasury_ledger_transactions WHERE chain=? ORDER BY ts_ms ASC, id ASC",
                (str(chain),),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                out.append(json.loads(r["payload_json"]))
            except (ValueError, TypeError):
                continue
        return out

    @staticmethod
    def _filter_prime_transactions(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in list(rows or [])
            if isinstance(row, dict) and str(row.get("tx_type") or "").startswith("prime_loan_")
        ]

    def all_transactions(self, *, chain: str) -> List[Dict[str, Any]]:
        return list(self._all_transactions(chain=chain))

    def prime_transactions(self, *, chain: str) -> List[Dict[str, Any]]:
        return self._filter_prime_transactions(self._all_transactions(chain=chain))

    def has_receipt_transaction(
        self,
        *,
        chain: str,
        receipt_id: str,
        tx_type: str = "receipt_settlement",
    ) -> bool:
        receipt = str(receipt_id or "")
        if not receipt:
            return False
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM treasury_ledger_transactions WHERE chain=? AND receipt_id=? AND tx_type=? LIMIT 1",
                (str(chain), receipt, str(tx_type or "receipt_settlement")),
            ).fetchone()
        return bool(row)

    def transaction_balance_report(self, *, chain: str) -> Dict[str, Any]:
        rows = self._all_transactions(chain=chain)
        accounting = TreasuryLedger._aggregate_accounting_semantics(rows)
        return {
            "balances": self._aggregate_transaction_balances(rows),
            "balanceSource": "transaction_journal" if rows else "repository_empty",
            "transactionCount": int(len(rows)),
            "accountBalances": accounting.get("accountBalances") or {},
            "accounting": {k: v for k, v in accounting.items() if k != "accountBalances"},
        }

    def transaction_balances(self, *, chain: str) -> Dict[str, float]:
        return dict(self.transaction_balance_report(chain=chain).get("balances") or {})

    def append(self, *, chain: str, payload: Dict[str, Any]) -> None:
        payload_dict = dict(payload or {})
        asset = str(payload_dict.get("asset") or "")
        amount = float(payload_dict.get("amount") or 0.0)
        entry_type = str(payload_dict.get("entry_type") or "")
        transaction_id = str(payload_dict.get("transaction_id") or f"tx_{uuid.uuid4().hex[:16]}")
        metadata = {
            "entry_type": entry_type,
            "asset": asset,
            "venue": str(payload_dict.get("venue") or ""),
            "family": str(payload_dict.get("family") or ""),
            "note": str(payload_dict.get("note") or ""),
            **dict(payload_dict.get("metadata") or {}),
        }
        tx_payload = {
            "transaction_id": transaction_id,
            "ts_ms": int(payload_dict.get("ts_ms") or int(time.time() * 1000)),
            "tx_type": entry_type,
            "receipt_id": str(payload_dict.get("receipt_id") or ""),
            "lines": [
                {
                    "account": f"asset:{asset}",
                    "asset": asset,
                    "amount": amount,
                    "family": str(payload_dict.get("family") or ""),
                    "venue": str(payload_dict.get("venue") or ""),
                    "note": str(payload_dict.get("note") or ""),
                },
                {
                    "account": "equity:offset",
                    "asset": "USD",
                    "amount": float(-amount),
                    "family": str(payload_dict.get("family") or ""),
                    "venue": str(payload_dict.get("venue") or ""),
                    "note": f"offset:{str(payload_dict.get('note') or entry_type)}",
                },
            ],
            "metadata": metadata,
        }
        self.append_transaction(chain=str(chain), payload=tx_payload)

    def _publish_capital_event(
        self, *, chain: str, payload: Dict[str, Any], conn: sqlite3.Connection | None = None
    ) -> None:
        repo = self._capital_event_repo
        if repo is None or not hasattr(repo, "append_event"):
            return
        payload_dict = dict(payload or {})
        metadata = dict(payload_dict.get("metadata") or {})
        lines = [
            dict(line) for line in list(payload_dict.get("lines") or []) if isinstance(line, dict)
        ]
        try:
            repo.append_event(
                ts_ms=int(payload_dict.get("ts_ms") or 0),
                domain="ledger",
                event_type=str(payload_dict.get("tx_type") or "transaction"),
                source="ledger_repository",
                transaction_id=str(payload_dict.get("transaction_id") or ""),
                receipt_id=str(payload_dict.get("receipt_id") or ""),
                entity_id=str(chain or self._default_chain or ""),
                conn=conn,
                payload={
                    "chain": str(chain or self._default_chain or ""),
                    "tx_type": str(payload_dict.get("tx_type") or "transaction"),
                    "line_count": int(len(lines)),
                    "accounts": [str(line.get("account") or "") for line in lines],
                    "metadata": metadata,
                },
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return

    def append_transaction(
        self,
        *,
        chain: str,
        payload: Dict[str, Any],
        conn: sqlite3.Connection | None = None,
        publish_capital_event: bool = True,
    ) -> None:
        payload_dict = dict(payload or {})
        chain_name = str(chain or self._default_chain or "")
        params = (
            chain_name,
            str(payload_dict.get("transaction_id") or ""),
            int(payload_dict.get("ts_ms") or 0),
            str(payload_dict.get("tx_type") or ""),
            str(payload_dict.get("receipt_id") or ""),
            json.dumps(payload_dict, sort_keys=True),
        )
        if conn is not None:
            conn.execute(
                "INSERT INTO treasury_ledger_transactions(chain, transaction_id, ts_ms, tx_type, receipt_id, payload_json) VALUES(?,?,?,?,?,?)",
                params,
            )
            if publish_capital_event:
                self._publish_capital_event(chain=chain_name, payload=payload_dict, conn=conn)
            return
        with self.db.connect() as owned_conn:
            owned_conn.execute(
                "INSERT INTO treasury_ledger_transactions(chain, transaction_id, ts_ms, tx_type, receipt_id, payload_json) VALUES(?,?,?,?,?,?)",
                params,
            )
        if publish_capital_event:
            self._publish_capital_event(chain=chain_name, payload=payload_dict)

    def tail(self, *, chain: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM treasury_ledger WHERE chain=? ORDER BY ts_ms DESC, id DESC LIMIT ?",
                (str(chain), int(limit)),
            ).fetchall()
        out = []
        for r in rows:
            try:
                out.append(json.loads(r["payload_json"]))
            except (ValueError, TypeError):
                continue
        if out:
            return out
        projected = TreasuryLedger.projected_entry_rows(self._all_transactions(chain=str(chain)))
        return projected[-max(1, int(limit)) :]

    def delete_transaction(self, *, chain: str, transaction_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "DELETE FROM treasury_ledger_transactions WHERE chain=? AND transaction_id=?",
                (str(chain), str(transaction_id)),
            )

    def transactions_tail(self, *, chain: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM treasury_ledger_transactions WHERE chain=? ORDER BY ts_ms DESC, id DESC LIMIT ?",
                (str(chain), int(limit)),
            ).fetchall()
        out = []
        for r in rows:
            try:
                out.append(json.loads(r["payload_json"]))
            except (ValueError, TypeError):
                continue
        return out
