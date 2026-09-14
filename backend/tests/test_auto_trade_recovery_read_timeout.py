import sqlite3
import time

from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.auto_trade_recovery_repository import AutoTradeRecoveryRepository


def test_auto_trade_recovery_reads_fail_closed_with_bounded_sqlite_lock_timeout(tmp_path):
    db = PersistenceDB(str(tmp_path / "state.db"))
    repo = AutoTradeRecoveryRepository(db, chain="ethereum")
    locker = sqlite3.connect(str(tmp_path / "state.db"), timeout=0, isolation_level=None)
    try:
        locker.execute("BEGIN EXCLUSIVE")

        started = time.monotonic()
        assert repo.load() == {}
        assert repo.recent_events() == []
        elapsed = time.monotonic() - started

        assert elapsed < 1.5
    finally:
        locker.rollback()
        locker.close()
