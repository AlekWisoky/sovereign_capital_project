from __future__ import annotations

from pathlib import Path

from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.bankroll_repository import BankrollEventRepository


def test_bankroll_manager_persists_native_timestamps_and_state(tmp_path, monkeypatch):
    state_path = Path(tmp_path) / "bankroll_state.json"
    times = iter([1_700_000_000.0, 1_700_000_060.0, 1_700_000_120.0, 1_700_000_180.0])
    monkeypatch.setattr("victor_ai_bot.bankroll.time.time", lambda: next(times))

    history_repo = BankrollEventRepository(
        PersistenceDB(str(Path(tmp_path) / "state.sqlite3")),
        chain="ethereum",
    )
    manager = BankrollManager(
        BankrollConfig(base_borrow_amount_wei=100, max_borrow_amount_wei=500),
        state_path=str(state_path),
        history_repo=history_repo,
    )
    manager.record_trade(success=True, realized_profit_after_gas_wei=25, amount_in_wei=100)
    amount = manager.next_amount_in()

    assert amount == 100
    assert manager.state.updated_ts_ms == 1_700_000_120_000
    assert manager.state.profit_updated_ts_ms == 1_700_000_060_000
    assert manager.state.sizing_updated_ts_ms == 1_700_000_120_000
    assert state_path.exists()

    latest_event = history_repo.latest_event()
    assert latest_event["event_type"] == "sizing_decision"
    assert latest_event["state"]["realized_profit_wei"] == 25
    assert latest_event["state"]["last_amount_in_wei"] == 100
    assert len(history_repo.tail(limit=10)) == 3

    restored = BankrollManager(
        BankrollConfig(base_borrow_amount_wei=100, max_borrow_amount_wei=500),
        state_path=str(state_path),
        history_repo=history_repo,
    )

    assert restored.state.realized_profit_wei == 25
    assert restored.state.last_amount_in_wei == 100
    assert restored.state.updated_ts_ms == 1_700_000_120_000
    assert restored.state.profit_updated_ts_ms == 1_700_000_060_000
    assert restored.state.sizing_updated_ts_ms == 1_700_000_120_000
