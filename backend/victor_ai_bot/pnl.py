from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from typing import Any, Dict, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  chain TEXT NOT NULL,
  opportunity_id TEXT NOT NULL,
  route_id TEXT,
  tx_hash TEXT,
  mode TEXT NOT NULL,
  dry_run INTEGER NOT NULL,
  ok INTEGER NOT NULL,
  reason TEXT NOT NULL,
  expected_gross_profit_wei TEXT NOT NULL,
  expected_profit_after_costs_wei TEXT NOT NULL,
  estimated_gas_cost_wei TEXT NOT NULL,
  flashloan_fee_wei TEXT NOT NULL,
  gas_limit INTEGER NOT NULL,
  max_fee_wei TEXT NOT NULL,
  priority_fee_wei TEXT NOT NULL,
  receipt_status INTEGER,
  gas_used INTEGER,
  effective_gas_price_wei TEXT,
  realized_gas_cost_wei TEXT,
  realized_gas_cost_in_profit_token_wei TEXT,
  realized_profit_after_gas_wei TEXT,
  realized_profit_token TEXT,
  realized_profit_token_wei TEXT,
  realized_provider INTEGER,
  realized_profit_usd_micro TEXT,
  realized_gas_cost_usd_micro TEXT,
  realized_profit_after_gas_usd_micro TEXT,
  strategy_type TEXT,
  income_stream TEXT,
  venue_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts);
CREATE INDEX IF NOT EXISTS idx_trades_tx ON trades(tx_hash);
"""

_COERCE_EXCEPTIONS = (TypeError, ValueError, OverflowError)
_CACHE_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_STATS_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)
_DB_EXCEPTIONS = (sqlite3.Error, OSError, RuntimeError, TypeError, ValueError)
_EVENT_DECODE_EXCEPTIONS = (AttributeError, ImportError, KeyError, TypeError, ValueError)


def _now() -> int:
    return int(time.time())


def _s(v: Any) -> str:
    if v is None:
        return "0"
    if isinstance(v, str):
        return v
    return str(v)


def _i(v: Any) -> int:
    try:
        return int(v)
    except _COERCE_EXCEPTIONS:
        return 0


class PnLStore:
    """Async-safe SQLite store via asyncio.to_thread (no external deps)."""

    def __init__(self, path: str):
        self.path = path
        self._init_done = False
        self._lock = asyncio.Lock()

        self._cache_ttl_s = 3.0
        self._cache: Dict[tuple, tuple] = {}  # (kind, window)->(ts_monotonic, payload)
        self._state: Dict[str, Dict[str, Any] | bool] = {
            "config": self._new_state_section(cacheTtlS=self._cache_ttl_s),
            "cache": self._new_state_section(),
            "db": self._new_state_section(),
            "parse": self._new_state_section(),
            "degraded": False,
        }

        try:
            self._cache_ttl_s = float(os.environ.get("VICTOR_PNL_CACHE_TTL_S", "3.0") or "3.0")
            self._mark_state("config", ok=True)
        except _COERCE_EXCEPTIONS as exc:
            self._cache_ttl_s = 3.0
            self._mark_state("config", ok=False, code="cache_ttl_invalid", error=exc)
        config_state = self._state.get("config")
        if isinstance(config_state, dict):
            config_state["cacheTtlS"] = float(self._cache_ttl_s)

        # Lightweight health stats used by runtime metrics.
        self._stats: Dict[str, Any] = {
            "db_queries": 0,
            "db_errors": 0,
            "last_db_ms": 0.0,
            "ema_db_ms": 0.0,
            "summary_cache_hits": 0,
            "summary_cache_misses": 0,
            "income_cache_hits": 0,
            "income_cache_misses": 0,
        }

    def _new_state_section(self, **extra: Any) -> Dict[str, Any]:
        state = {
            "ok": True,
            "last_error_code": None,
            "last_error": None,
            "last_success_ts": None,
        }
        state.update(extra)
        return state

    def _update_degraded(self) -> None:
        sections = [
            payload
            for key, payload in self._state.items()
            if key != "degraded" and isinstance(payload, dict)
        ]
        self._state["degraded"] = any(not bool(section.get("ok", True)) for section in sections)

    def _mark_state(
        self,
        section: str,
        *,
        ok: bool,
        code: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        payload = self._state.get(section)
        if not isinstance(payload, dict):
            payload = self._new_state_section()
            self._state[section] = payload
        payload["ok"] = bool(ok)
        if ok:
            payload["last_error_code"] = None
            payload["last_error"] = None
            payload["last_success_ts"] = _now()
        else:
            payload["last_error_code"] = str(code or "error")
            payload["last_error"] = str(error or code or "error")
        self._update_degraded()

    def state(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for key, value in self._state.items():
            payload[key] = dict(value) if isinstance(value, dict) else bool(value)
        payload["degraded"] = bool(self._state.get("degraded", False))
        return payload

    def stats(self) -> Dict[str, Any]:
        """Return a snapshot of internal store health stats."""
        payload = dict(self._stats)
        payload["state"] = self.state()
        return payload

    def _cache_get(self, kind: str, window: int) -> Dict[str, Any] | None:
        try:
            key = (str(kind), int(window))
            hit = self._cache.get(key)
            if not hit:
                return None
            ts, payload = hit
            if (time.monotonic() - float(ts)) > float(self._cache_ttl_s):
                self._cache.pop(key, None)
                return None
            self._mark_state("cache", ok=True)
            return dict(payload)
        except _CACHE_EXCEPTIONS as exc:
            self._mark_state("cache", ok=False, code="cache_read_failed", error=exc)
            return None

    def _cache_set(self, kind: str, window: int, payload: Dict[str, Any]) -> None:
        try:
            key = (str(kind), int(window))
            self._cache[key] = (float(time.monotonic()), dict(payload))
            self._mark_state("cache", ok=True)
        except _CACHE_EXCEPTIONS as exc:
            self._mark_state("cache", ok=False, code="cache_write_failed", error=exc)

    def _invalidate_rollups(self) -> None:
        self._cache = {k: v for k, v in self._cache.items() if k[0] not in {"summary", "income"}}
        self._mark_state("cache", ok=True)

    def _record_db_timing(self, dt_ms: float, *, ok: bool) -> None:
        try:
            dt_ms_f = float(max(0.0, float(dt_ms)))
            self._stats["last_db_ms"] = dt_ms_f
            prev = float(self._stats.get("ema_db_ms", 0.0) or 0.0)
            alpha = 0.20
            self._stats["ema_db_ms"] = float(prev * (1.0 - alpha) + dt_ms_f * alpha)
            if ok:
                self._stats["db_queries"] = int(self._stats.get("db_queries", 0) or 0) + 1
            else:
                self._stats["db_errors"] = int(self._stats.get("db_errors", 0) or 0) + 1
        except _STATS_EXCEPTIONS as exc:
            self._mark_state("parse", ok=False, code="stats_update_failed", error=exc)

    def _safe_int(self, value: Any, *, code: str, default: int = 0) -> int:
        try:
            return int(str(value or "0"))
        except _COERCE_EXCEPTIONS as exc:
            self._mark_state("parse", ok=False, code=code, error=exc)
            return int(default)

    async def init(self) -> None:
        async with self._lock:
            if self._init_done:
                return

            def _init() -> None:
                con = sqlite3.connect(self.path)
                try:
                    con.execute("PRAGMA journal_mode=WAL;")
                    con.executescript(SCHEMA)
                    # Additive migrations for older DB files.
                    cols = [r[1] for r in con.execute("PRAGMA table_info(trades)").fetchall()]

                    def add_col(name: str, ddl: str) -> None:
                        if name not in cols:
                            con.execute(f"ALTER TABLE trades ADD COLUMN {ddl}")

                    add_col("route_id", "route_id TEXT")
                    add_col("realized_profit_token", "realized_profit_token TEXT")
                    add_col("realized_profit_token_wei", "realized_profit_token_wei TEXT")
                    add_col(
                        "realized_gas_cost_in_profit_token_wei",
                        "realized_gas_cost_in_profit_token_wei TEXT",
                    )
                    add_col("realized_provider", "realized_provider INTEGER")
                    add_col("realized_profit_usd_micro", "realized_profit_usd_micro TEXT")
                    add_col("realized_gas_cost_usd_micro", "realized_gas_cost_usd_micro TEXT")
                    add_col(
                        "realized_profit_after_gas_usd_micro",
                        "realized_profit_after_gas_usd_micro TEXT",
                    )
                    add_col("strategy_type", "strategy_type TEXT")
                    add_col("income_stream", "income_stream TEXT")
                    add_col("venue_path", "venue_path TEXT")
                    con.commit()
                finally:
                    con.close()

            t0 = time.perf_counter()
            try:
                await asyncio.to_thread(_init)
                self._init_done = True
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=True)
                self._mark_state("db", ok=True)
            except _DB_EXCEPTIONS as exc:
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=False)
                self._mark_state("db", ok=False, code="db_init_failed", error=exc)
                raise

    async def add_trade(self, row: Dict[str, Any]) -> int:
        await self.init()
        async with self._lock:

            def _add() -> int:
                con = sqlite3.connect(self.path)
                try:
                    cols = [
                        "ts",
                        "chain",
                        "opportunity_id",
                        "route_id",
                        "tx_hash",
                        "mode",
                        "dry_run",
                        "ok",
                        "reason",
                        "expected_gross_profit_wei",
                        "expected_profit_after_costs_wei",
                        "estimated_gas_cost_wei",
                        "flashloan_fee_wei",
                        "gas_limit",
                        "max_fee_wei",
                        "priority_fee_wei",
                        "strategy_type",
                        "income_stream",
                        "venue_path",
                    ]
                    vals = [
                        _i(row.get("ts", _now())),
                        str(row.get("chain", "")),
                        str(row.get("opportunity_id", "")),
                        str(row.get("route_id") or ""),
                        row.get("tx_hash"),
                        str(row.get("mode", "manual")),
                        1 if bool(row.get("dry_run", True)) else 0,
                        1 if bool(row.get("ok", False)) else 0,
                        str(row.get("reason", "")),
                        _s(row.get("expected_gross_profit_wei", "0")),
                        _s(row.get("expected_profit_after_costs_wei", "0")),
                        _s(row.get("estimated_gas_cost_wei", "0")),
                        _s(row.get("flashloan_fee_wei", "0")),
                        _i(row.get("gas_limit", 0)),
                        _s(row.get("max_fee_wei", "0")),
                        _s(row.get("priority_fee_wei", "0")),
                        _s(row.get("strategy_type", "")),
                        _s(row.get("income_stream", "")),
                        _s(row.get("venue_path", "")),
                    ]
                    q = f"INSERT INTO trades ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})"
                    cur = con.execute(q, vals)
                    con.commit()
                    return int(cur.lastrowid)
                finally:
                    con.close()

            t0 = time.perf_counter()
            try:
                rid = await asyncio.to_thread(_add)
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=True)
                self._mark_state("db", ok=True)
                self._invalidate_rollups()
                return rid
            except _DB_EXCEPTIONS as exc:
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=False)
                self._mark_state("db", ok=False, code="db_add_trade_failed", error=exc)
                raise

    async def update_receipt(
        self,
        tx_hash: str,
        receipt: Dict[str, Any],
        *,
        executor_address: str = "",
        chain_weth: str = "",
        realized_gas_cost_in_profit_token_wei: Optional[int] = None,
        realized_profit_usd_micro: Optional[int] = None,
        realized_gas_cost_usd_micro: Optional[int] = None,
        realized_profit_after_gas_usd_micro: Optional[int] = None,
    ) -> Dict[str, Any]:
        await self.init()
        async with self._lock:

            def _upd() -> Dict[str, Any]:
                con = sqlite3.connect(self.path)
                try:
                    status_hex = receipt.get("status")
                    status = int(status_hex, 16) if isinstance(status_hex, str) else None
                    gas_used_hex = receipt.get("gasUsed")
                    gas_used = int(gas_used_hex, 16) if isinstance(gas_used_hex, str) else None
                    eff_hex = receipt.get("effectiveGasPrice") or receipt.get("gasPrice")
                    eff = int(eff_hex, 16) if isinstance(eff_hex, str) else None
                    realized_gas_cost = str((gas_used or 0) * (eff or 0))

                    realized_profit_token = None
                    realized_profit_token_wei = None
                    realized_provider = None
                    realized_after_gas = None
                    realized_gas_cost_in_profit = None
                    # Decode executor event if possible.
                    if executor_address:
                        try:
                            from .executor_events import decode_arb_executed

                            logs = receipt.get("logs") or []
                            ex = executor_address.lower()
                            for lg in logs:
                                if not isinstance(lg, dict):
                                    continue
                                addr = str(lg.get("address") or "").lower()
                                if addr != ex:
                                    continue
                                ev = decode_arb_executed(lg)
                                if ev is None:
                                    continue
                                realized_profit_token = ev.token
                                realized_profit_token_wei = str(int(ev.profit))
                                realized_provider = int(ev.provider)
                                # Compute net-after-gas in profit-token units when possible.
                                if realized_gas_cost_in_profit_token_wei is not None:
                                    realized_gas_cost_in_profit = str(
                                        int(realized_gas_cost_in_profit_token_wei)
                                    )
                                elif chain_weth and ev.token.lower() == chain_weth.lower():
                                    realized_gas_cost_in_profit = str(int(realized_gas_cost))

                                if realized_gas_cost_in_profit is not None:
                                    realized_after_gas = str(
                                        max(0, int(ev.profit) - int(realized_gas_cost_in_profit))
                                    )
                                break
                        except _EVENT_DECODE_EXCEPTIONS as exc:
                            self._mark_state(
                                "parse",
                                ok=False,
                                code="receipt_event_decode_failed",
                                error=exc,
                            )

                    con.execute(
                        "UPDATE trades SET receipt_status=?, gas_used=?, effective_gas_price_wei=?, realized_gas_cost_wei=?, realized_gas_cost_in_profit_token_wei=?, realized_profit_after_gas_wei=?, realized_profit_token=?, realized_profit_token_wei=?, realized_provider=?, realized_profit_usd_micro=?, realized_gas_cost_usd_micro=?, realized_profit_after_gas_usd_micro=? WHERE tx_hash=?",
                        (
                            status,
                            gas_used,
                            str(eff or 0),
                            realized_gas_cost,
                            realized_gas_cost_in_profit,
                            realized_after_gas,
                            realized_profit_token,
                            realized_profit_token_wei,
                            realized_provider,
                            (
                                str(int(realized_profit_usd_micro))
                                if realized_profit_usd_micro is not None
                                else None
                            ),
                            (
                                str(int(realized_gas_cost_usd_micro))
                                if realized_gas_cost_usd_micro is not None
                                else None
                            ),
                            (
                                str(int(realized_profit_after_gas_usd_micro))
                                if realized_profit_after_gas_usd_micro is not None
                                else None
                            ),
                            tx_hash,
                        ),
                    )
                    con.commit()
                    return {
                        "status": status,
                        "gas_used": gas_used,
                        "effective_gas_price_wei": str(eff or 0),
                        "realized_gas_cost_wei": realized_gas_cost,
                        "realized_gas_cost_in_profit_token_wei": realized_gas_cost_in_profit,
                        "realized_profit_token": realized_profit_token,
                        "realized_profit_token_wei": realized_profit_token_wei,
                        "realized_profit_after_gas_wei": realized_after_gas,
                        "realized_provider": realized_provider,
                        "realized_profit_usd_micro": (
                            str(int(realized_profit_usd_micro))
                            if realized_profit_usd_micro is not None
                            else None
                        ),
                        "realized_gas_cost_usd_micro": (
                            str(int(realized_gas_cost_usd_micro))
                            if realized_gas_cost_usd_micro is not None
                            else None
                        ),
                        "realized_profit_after_gas_usd_micro": (
                            str(int(realized_profit_after_gas_usd_micro))
                            if realized_profit_after_gas_usd_micro is not None
                            else None
                        ),
                    }
                finally:
                    con.close()

            t0 = time.perf_counter()
            try:
                out = await asyncio.to_thread(_upd)
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=True)
                self._mark_state("db", ok=True)
                self._invalidate_rollups()
                return out
            except _DB_EXCEPTIONS as exc:
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=False)
                self._mark_state("db", ok=False, code="db_update_receipt_failed", error=exc)
                raise

    async def summary(self, window: int = 50) -> Dict[str, Any]:
        await self.init()
        cached = self._cache_get("summary", int(window))
        if cached is not None:
            self._stats["summary_cache_hits"] = (
                int(self._stats.get("summary_cache_hits", 0) or 0) + 1
            )
            return cached
        self._stats["summary_cache_misses"] = (
            int(self._stats.get("summary_cache_misses", 0) or 0) + 1
        )
        async with self._lock:

            def _get() -> Dict[str, Any]:
                con = sqlite3.connect(self.path)
                con.row_factory = sqlite3.Row
                try:
                    cur = con.execute(
                        "SELECT * FROM trades ORDER BY ts DESC, id DESC LIMIT ?", (int(window),)
                    )
                    rows = [dict(r) for r in cur.fetchall()]
                finally:
                    con.close()
                total_realized = 0
                total_realized_usd = 0
                total_expected_after = 0
                succ = 0
                n = len(rows)
                for r in rows:
                    exp_after = self._safe_int(
                        r.get("expected_profit_after_costs_wei"),
                        code="summary_expected_profit_invalid",
                    )
                    total_expected_after += exp_after
                    realized = r.get("realized_profit_after_gas_wei")
                    if realized is not None:
                        total_realized += self._safe_int(
                            realized,
                            code="summary_realized_profit_invalid",
                        )
                    realized_usd = r.get("realized_profit_after_gas_usd_micro")
                    if realized_usd is not None:
                        total_realized_usd += self._safe_int(
                            realized_usd,
                            code="summary_realized_usd_invalid",
                        )
                    status = r.get("receipt_status")
                    if status == 1 or (
                        status is None
                        and int(r.get("dry_run") or 0) == 1
                        and int(r.get("ok") or 0) == 1
                    ):
                        succ += 1
                efficiency = (
                    (total_realized / total_expected_after * 100.0)
                    if total_expected_after > 0
                    else 0.0
                )
                success_rate = (succ / n * 100.0) if n > 0 else 0.0
                return {
                    "window": window,
                    "n": n,
                    "succeeded": succ,
                    "success_rate_pct": round(success_rate, 2),
                    "expected_profit_after_costs_wei": str(total_expected_after),
                    "realized_profit_after_gas_wei": str(total_realized),
                    "realized_profit_after_gas_usd_micro": str(total_realized_usd),
                    "efficiency_pct": round(efficiency, 2),
                    "recent": rows[: min(20, len(rows))],
                }

            t0 = time.perf_counter()
            try:
                out = await asyncio.to_thread(_get)
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=True)
                self._mark_state("db", ok=True)
                self._cache_set("summary", int(window), out)
                return out
            except _DB_EXCEPTIONS as exc:
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=False)
                self._mark_state("db", ok=False, code="db_summary_failed", error=exc)
                raise

    async def income_breakdown(self, window: int = 3600) -> Dict[str, Any]:
        """Compute income stream breakdown over the given window (seconds)."""
        await self.init()
        cached = self._cache_get("income", int(window))
        if cached is not None:
            self._stats["income_cache_hits"] = int(self._stats.get("income_cache_hits", 0) or 0) + 1
            return cached
        self._stats["income_cache_misses"] = int(self._stats.get("income_cache_misses", 0) or 0) + 1
        cutoff = _now() - int(window)
        async with self._lock:

            def _q() -> Dict[str, Any]:
                con = sqlite3.connect(self.path)
                try:
                    cur = con.cursor()
                    cur.execute(
                        "SELECT income_stream, strategy_type, ok, realized_profit_after_gas_wei, ts FROM trades WHERE ts >= ? ORDER BY ts DESC",
                        (cutoff,),
                    )
                    rows = cur.fetchall() or []
                finally:
                    con.close()
                # columns: income_stream, strategy_type, ok, realized_profit_after_gas_wei, ts
                by_stream: Dict[str, Dict[str, Any]] = {}
                by_strategy: Dict[str, Dict[str, Any]] = {}
                total_pnl = 0
                total_n = 0
                total_wins = 0
                for r in rows:
                    stream = str(r[0] or "unknown")
                    stype = str(r[1] or "unknown")
                    ok = bool(self._safe_int(r[2], code="income_ok_invalid"))
                    pnl = self._safe_int(r[3], code="income_realized_profit_invalid")
                    total_pnl += pnl
                    total_n += 1
                    if ok:
                        total_wins += 1

                    if stream not in by_stream:
                        by_stream[stream] = {"n": 0, "wins": 0, "pnl_wei": 0}
                    by_stream[stream]["n"] += 1
                    by_stream[stream]["pnl_wei"] += pnl
                    if ok:
                        by_stream[stream]["wins"] += 1

                    if stype not in by_strategy:
                        by_strategy[stype] = {"n": 0, "wins": 0, "pnl_wei": 0}
                    by_strategy[stype]["n"] += 1
                    by_strategy[stype]["pnl_wei"] += pnl
                    if ok:
                        by_strategy[stype]["wins"] += 1

                # add win_rate
                for d in list(by_stream.values()):
                    n = float(d.get("n") or 0)
                    d["win_rate"] = float(d.get("wins") or 0) / n if n > 0 else 0.0
                for d in list(by_strategy.values()):
                    n = float(d.get("n") or 0)
                    d["win_rate"] = float(d.get("wins") or 0) / n if n > 0 else 0.0

                return {
                    "window_s": int(window),
                    "trades": int(total_n),
                    "wins": int(total_wins),
                    "win_rate": float(total_wins / total_n) if total_n > 0 else 0.0,
                    "pnl_total_wei": str(total_pnl),
                    "by_income_stream": by_stream,
                    "by_strategy_type": by_strategy,
                }

            t0 = time.perf_counter()
            try:
                out = await asyncio.to_thread(_q)
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=True)
                self._mark_state("db", ok=True)
                self._cache_set("income", int(window), out)
                return out
            except _DB_EXCEPTIONS as exc:
                self._record_db_timing((time.perf_counter() - t0) * 1000.0, ok=False)
                self._mark_state("db", ok=False, code="db_income_breakdown_failed", error=exc)
                raise
