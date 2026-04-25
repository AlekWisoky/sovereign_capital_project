from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from victor_ai_bot.pnl import PnLStore
from victor_ai_bot.runtime_services.state_summary_service import StateSummaryService


def _store(tmp_path: Path) -> PnLStore:
    return PnLStore(str(tmp_path / "pnl.sqlite"))


def test_pnl_summary_degrades_cleanly_on_malformed_realized_values(tmp_path: Path):
    async def _run() -> None:
        store = _store(tmp_path)
        row_id = await store.add_trade(
            {
                "ts": 1,
                "chain": "eth",
                "opportunity_id": "opp-1",
                "mode": "auto",
                "dry_run": False,
                "ok": True,
                "reason": "ok",
                "expected_profit_after_costs_wei": "100",
            }
        )
        con = sqlite3.connect(store.path)
        try:
            con.execute(
                "UPDATE trades SET realized_profit_after_gas_wei=?, realized_profit_after_gas_usd_micro=? WHERE id=?",
                ("bad-wei", "bad-usd", row_id),
            )
            con.commit()
        finally:
            con.close()

        out = await store.summary(window=10)
        assert out["n"] == 1
        assert out["realized_profit_after_gas_wei"] == "0"
        assert out["realized_profit_after_gas_usd_micro"] == "0"
        state = store.state()
        assert state["degraded"] is True
        assert state["parse"]["last_error_code"] == "summary_realized_usd_invalid"

    asyncio.run(_run())


def test_state_summary_service_surfaces_pnl_storage_state(tmp_path: Path):
    async def _run() -> None:
        store = _store(tmp_path)
        await store.init()
        with patch(
            "victor_ai_bot.pnl.sqlite3.connect", side_effect=sqlite3.OperationalError("disk full")
        ):
            try:
                await store.summary(window=10)
            except sqlite3.OperationalError:
                pass

        runtime = SimpleNamespace(
            _telemetry_service=SimpleNamespace(
                service_health=lambda runtime: {"execution": {"ok": True}}
            ),
            _pnl=store,
        )
        payload = StateSummaryService().service_health(runtime)
        assert payload["pnl"]["ok"] is True
        assert payload["pnl"]["status"] == "degraded"
        assert payload["pnl"]["degraded"] is True
        assert payload["pnl"]["reason_code"] == "db_summary_failed"
        assert payload["pnl"]["storage"]["db"]["last_error_code"] == "db_summary_failed"

    asyncio.run(_run())
