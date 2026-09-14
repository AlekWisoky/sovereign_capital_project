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
    _READ_FAILURE_REASON = "auto_trade_recovery_read_failed"
    _READ_FAILURE_NEXT_ACTION = "restore_auto_trade_recovery_state"

    def _bounded_reader(self) -> _AutoTradeRecoveryRepository:
        return _AutoTradeRecoveryRepository(
            _BoundedReadDB(self.db, busy_timeout_ms=self._READ_BUSY_TIMEOUT_MS),
            chain=self.chain,
        )

    @classmethod
    def _read_failure_state(cls) -> Dict[str, Any]:
        reason = cls._READ_FAILURE_REASON
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 0,
            "last_recovered_ts_ms": 0,
            "degraded_count": 0,
            "last_healthy_ts_ms": 0,
            "updated_ts_ms": 0,
            "history_status": "blocked",
            "last_reason_code": reason,
            "last_stage": "persistence_read",
            "last_blocker_component": "auto_trade_recovery",
            "last_next_action": cls._READ_FAILURE_NEXT_ACTION,
            "last_reason_codes": [reason],
            "history_component": "auto_trade_recovery",
            "history_stage": "persistence_read",
            "history_reason_code": reason,
            "history_reason_codes": [reason],
            "history_next_action": cls._READ_FAILURE_NEXT_ACTION,
            "reliability_class": "unavailable",
            "reliability_reason_code": reason,
            "reliability_reason_codes": [reason],
            "reliability_next_action": cls._READ_FAILURE_NEXT_ACTION,
            "component_reliability_class": "unavailable",
            "component_reliability_reason_code": reason,
            "component_reliability_reason_codes": [reason],
            "component_reliability_next_action": cls._READ_FAILURE_NEXT_ACTION,
            "component_recovered_fragile": False,
            "family_hardening_reason_codes": [],
            "receipt_outcome_truth_reason_codes": [],
        }

    def load(self, component: str = "auto_trade_admission") -> Dict[str, Any]:
        try:
            return self._bounded_reader().load(component)
        except sqlite3.Error:
            return self._read_failure_state()

    def recent_events(
        self, component: str = "auto_trade_admission", *, limit: int = 10
    ) -> List[Dict[str, Any]]:
        try:
            return self._bounded_reader().recent_events(component, limit=limit)
        except sqlite3.Error:
            return []
