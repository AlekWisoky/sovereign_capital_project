from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any, Dict, List


def _utc_day(ts_ms: int) -> str:
    return datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class DrawdownStateStore:
    def __init__(
        self,
        *,
        data_dir: str,
        chain: str,
        intraday_loss_limit_usd: float = 250.0,
        intraday_drawdown_limit_pct: float = 0.05,
    ):
        self.chain = str(chain)
        self.intraday_loss_limit_usd = float(intraday_loss_limit_usd)
        self.intraday_drawdown_limit_pct = float(intraday_drawdown_limit_pct)
        self._path = os.path.join(data_dir, "risk", f"drawdown_{self.chain}.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._state = self._load()

    def _blank(self) -> Dict[str, Any]:
        return {
            "equity_curve": [],
            "family_returns": {},
            "regime_returns": {},
            "route_family_drawdown": {},
            "venue_drawdown": {},
            "lane_drawdown": {},
            "hard_stop": {"active": False, "reason_codes": [], "triggered_ts_ms": 0},
        }

    def _coerce_state(self, data: Any) -> Dict[str, Any]:
        blank = self._blank()
        if not isinstance(data, dict):
            return blank

        for key in (
            "equity_curve",
            "family_returns",
            "regime_returns",
            "route_family_drawdown",
            "venue_drawdown",
            "lane_drawdown",
        ):
            value = data.get(key)
            if isinstance(value, type(blank[key])):
                blank[key] = value

        hard_stop = data.get("hard_stop")
        if isinstance(hard_stop, dict):
            blank["hard_stop"] = {
                "active": bool(hard_stop.get("active", False)),
                "reason_codes": [str(x) for x in list(hard_stop.get("reason_codes") or [])],
                "triggered_ts_ms": int(hard_stop.get("triggered_ts_ms") or 0),
            }
        return blank

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            return self._blank()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return self._coerce_state(data)
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()

    def _persist(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _append_return(self, section: str, key: str, value: float) -> None:
        bucket = list(
            ((self._state.get(section) or {}) if isinstance(self._state, dict) else {}).get(key)
            or []
        )
        bucket.append(round(float(value), 6))
        self._state.setdefault(section, {})[key] = bucket[-250:]

    def observe(
        self,
        *,
        family: str,
        route_family: str,
        venue: str,
        lane: str,
        regime: str,
        realized_pnl_usd: float,
        ts_ms: int | None = None,
    ) -> Dict[str, Any]:
        ts_ms = int(ts_ms or time.time() * 1000)
        equity = list(self._state.get("equity_curve") or [])
        running = float(equity[-1]["equity"] if equity else 0.0) + float(realized_pnl_usd)
        equity.append(
            {
                "ts_ms": ts_ms,
                "equity": round(running, 6),
                "pnl": round(float(realized_pnl_usd), 6),
                "day": _utc_day(ts_ms),
            }
        )
        self._state["equity_curve"] = equity[-500:]
        self._append_return("family_returns", str(family or "unknown"), float(realized_pnl_usd))
        self._append_return("regime_returns", str(regime or "unknown"), float(realized_pnl_usd))
        self._append_return(
            "route_family_drawdown", str(route_family or "unknown"), float(realized_pnl_usd)
        )
        self._append_return("venue_drawdown", str(venue or "unknown"), float(realized_pnl_usd))
        self._append_return("lane_drawdown", str(lane or "unknown"), float(realized_pnl_usd))
        snap = self.snapshot()
        reasons: List[str] = []
        if float(snap["intradayLossUsd"]) <= -abs(self.intraday_loss_limit_usd):
            reasons.append("intraday_loss_limit")
        if float(snap["intradayDrawdownPct"]) >= abs(self.intraday_drawdown_limit_pct):
            reasons.append("intraday_drawdown_limit")
        if reasons:
            self._state["hard_stop"] = {
                "active": True,
                "reason_codes": reasons,
                "triggered_ts_ms": ts_ms,
            }
        self._persist()
        return snap

    def snapshot(self) -> Dict[str, Any]:
        equity = list(self._state.get("equity_curve") or [])
        peak = max([float(x.get("equity") or 0.0) for x in equity] + [0.0])
        current = float(equity[-1]["equity"]) if equity else 0.0
        drawdown_abs = peak - current
        drawdown_pct = (
            drawdown_abs / float(max(1.0, abs(peak))) if peak > 0 else (1.0 if current < 0 else 0.0)
        )
        today = _utc_day(int(time.time() * 1000))
        today_rows = [x for x in equity if str(x.get("day") or "") == today]
        intraday_loss = sum(float(x.get("pnl") or 0.0) for x in today_rows)
        day_running = 0.0
        day_peak = 0.0
        day_worst = 0.0
        for row in today_rows:
            day_running += float(row.get("pnl") or 0.0)
            day_peak = max(day_peak, day_running)
            day_worst = min(day_worst, day_running - day_peak)
        intraday_dd_pct = (
            abs(day_worst)
            / float(max(1.0, abs(day_peak) if day_peak else max(1.0, abs(intraday_loss))))
            if today_rows
            else 0.0
        )

        def _section_drawdown(section: str) -> Dict[str, float]:
            out: Dict[str, float] = {}
            for key, series in sorted((self._state.get(section) or {}).items()):
                running = 0.0
                peak_val = 0.0
                worst = 0.0
                for value in list(series or [])[-90:]:
                    running += float(value or 0.0)
                    peak_val = max(peak_val, running)
                    worst = min(worst, running - peak_val)
                out[str(key)] = round(abs(worst), 6)
            return out

        return {
            "drawdownPct": round(_clip(drawdown_pct, 0.0, 5.0), 6),
            "drawdownUsd": round(drawdown_abs, 6),
            "intradayLossUsd": round(intraday_loss, 6),
            "intradayDrawdownPct": round(_clip(intraday_dd_pct, 0.0, 5.0), 6),
            "familyDrawdown": _section_drawdown("family_returns"),
            "familyReturnHistory": {
                k: list(v)[-60:]
                for k, v in sorted((self._state.get("family_returns") or {}).items())
            },
            "routeFamilyDrawdown": _section_drawdown("route_family_drawdown"),
            "venueDrawdown": _section_drawdown("venue_drawdown"),
            "laneDrawdown": _section_drawdown("lane_drawdown"),
            "regimeDrawdown": _section_drawdown("regime_returns"),
            "regimeReturnHistory": {
                k: list(v)[-60:]
                for k, v in sorted((self._state.get("regime_returns") or {}).items())
            },
            "hardStop": dict(self._state.get("hard_stop") or {}),
        }

    def gate(self, *, family: str) -> Dict[str, Any]:
        snap = self.snapshot()
        reasons = list((snap.get("hardStop") or {}).get("reason_codes") or [])
        family_drawdown = float(
            (snap.get("familyDrawdown") or {}).get(str(family or "unknown")) or 0.0
        )
        if family_drawdown >= max(25.0, abs(self.intraday_loss_limit_usd) * 0.35):
            reasons.append("family_drawdown_stop")
        return {
            "allowed": not bool(reasons),
            "reason_codes": sorted(set(reasons)),
            "aggressiveness_cap": 0.35 if reasons else (0.70 if family_drawdown > 0 else 1.0),
            "snapshot": snap,
        }
