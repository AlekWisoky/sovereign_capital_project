import sqlite3
import time

from victor_ai_bot.persistence.db import PersistenceDB


def test_recovery_table_read_is_bounded_under_sqlite_lock(tmp_path):
    db_path = tmp_path / "state.db"
    db = PersistenceDB(str(db_path))

    locker = sqlite3.connect(str(db_path), timeout=0, isolation_level=None)
    try:
        locker.execute("PRAGMA journal_mode=DELETE")
        locker.execute("BEGIN EXCLUSIVE")

        started = time.monotonic()
        try:
            with db.connect() as conn:
                conn.execute(
                    "SELECT payload_json FROM auto_trade_recovery_state "
                    "WHERE chain=? AND component=?",
                    ("ethereum", "auto_trade_admission"),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            elapsed = time.monotonic() - started
            assert "locked" in str(exc).lower()
            assert elapsed < 1.5
        else:
            raise AssertionError("expected the locked recovery read to fail closed")
    finally:
        locker.rollback()
        locker.close()
