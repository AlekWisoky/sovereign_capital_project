from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

from ._auto_trade_recovery_repository_impl import AutoTradeRecoveryRepository as _AutoTradeRecoveryRepository


class _BoundedReadDB:
    def __init__(self, db: Any, *, busy_timeout_ms: int):
        self._db = db
        self._busy_timeout_ms = int(busy_timeout_ms)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = self._db._connect()
        try:
            conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
            yield conn
        finally:
            conn.close()


class AutoTradeRecoveryRepository(_AutoTradeRecoveryRepository):
    """Recovery repository with bounded, read-only SQLite access."""

    _READ_BUSY_TIMEOUT_MS = 500

    def _bounded_reader(self) -> _AutoTradeRecoveryRepository:
        return _AutoTradeRecoveryRepository(
            _BoundedReadDB(self.db, busy_timeout_ms=self._READ_BUSY_TIMEOUT_MS),
            chain=self.chain,
        )

    def load(self, component: str = "auto_trade_admission") -> Dict[str, Any]:
        try:
            return self._bounded_reader().load(component)
        except sqlite3.Error:
            return {}

    def recent_events(
        self, component: str = "auto_trade_admission", *, limit: int = 10
    ) -> List[Dict[str, Any]]:
        try:
            return self._bounded_reader().recent_events(component, limit=limit)
        except sqlite3.Error:
            return []
