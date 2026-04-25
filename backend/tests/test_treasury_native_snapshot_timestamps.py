from __future__ import annotations

from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.treasury.config import TreasuryConfig
from victor_ai_bot.treasury.runtime import TreasuryRuntime


def test_treasury_runtime_stamps_and_persists_native_snapshot_timestamps(tmp_path, monkeypatch):
    monkeypatch.setattr("victor_ai_bot.treasury.runtime.time.time", lambda: 1_700_000_000.0)
    cfg = TreasuryConfig(enabled=True)
    db = PersistenceDB(str(tmp_path / "state.sqlite3"))
    runtime = TreasuryRuntime(cfg=cfg, data_dir=str(tmp_path), db=db, chain="ethereum")

    snapshot = runtime.pre_select_strategy(
        bankroll_state={
            "realized_profit_wei": 0,
            "last_amount_in_wei": 100,
            "updated_ts_ms": 1_699_999_940_000,
            "profit_updated_ts_ms": 1_699_999_940_000,
            "sizing_updated_ts_ms": 1_699_999_940_000,
        },
        volatility_regime="balanced",
    )

    assert snapshot["updated_ts_ms"] == 1_700_000_000_000
    assert snapshot["bankroll_state_ts_ms"] == 1_699_999_940_000
    assert snapshot["capital_engine"]["updated_ts_ms"] == 1_700_000_000_000
    assert snapshot["capital_engine"]["bankroll_state_ts_ms"] == 1_699_999_940_000
    assert snapshot["reinvestment_policy"]["updated_ts_ms"] == 1_700_000_000_000
    assert snapshot["capital_efficiency_metrics"]["updated_ts_ms"] == 1_700_000_000_000

    latest_history = runtime._state_repo.latest(state_type="capital_snapshot")
    assert latest_history["ts_ms"] == 1_700_000_000_000
    assert latest_history["payload"]["capital_engine"]["updated_ts_ms"] == 1_700_000_000_000

    restored = TreasuryRuntime(cfg=cfg, data_dir=str(tmp_path), db=db, chain="ethereum")
    restored_snapshot = restored.snapshot()
    assert restored_snapshot["updated_ts_ms"] == 1_700_000_000_000
    assert restored_snapshot["capital_engine"]["updated_ts_ms"] == 1_700_000_000_000
    assert (
        restored._state_repo.latest(state_type="capital_snapshot")["payload"]["updated_ts_ms"]
        == 1_700_000_000_000
    )
