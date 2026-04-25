from __future__ import annotations

import json
import os
from json import JSONDecodeError
from typing import Any, Dict


class NoTradeAnalytics:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._state = self._load()

    def _blank(self) -> Dict[str, Any]:
        return {
            "false_admissions": 0,
            "false_drops": 0,
            "conservatism_cost_usd": 0.0,
            "bad_trade_avoidance_value_usd": 0.0,
        }

    def _coerce_state(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return self._blank()

        state = self._blank()
        for key in ("false_admissions", "false_drops"):
            try:
                state[key] = max(0, int(data.get(key) or 0))
            except (TypeError, ValueError):
                state[key] = 0
        for key in ("conservatism_cost_usd", "bad_trade_avoidance_value_usd"):
            try:
                state[key] = float(data.get(key) or 0.0)
            except (TypeError, ValueError):
                state[key] = 0.0
        return state

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()
        return self._coerce_state(data)

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def observe(self, *, admitted: bool, projected_edge_usd: float, actual_edge_usd: float) -> None:
        if admitted and actual_edge_usd < 0.0:
            self._state["false_admissions"] = int(self._state.get("false_admissions") or 0) + 1
            self._state["bad_trade_avoidance_value_usd"] = float(
                self._state.get("bad_trade_avoidance_value_usd") or 0.0
            ) + abs(float(actual_edge_usd))
        if (not admitted) and projected_edge_usd > 0.0:
            self._state["false_drops"] = int(self._state.get("false_drops") or 0) + 1
            self._state["conservatism_cost_usd"] = float(
                self._state.get("conservatism_cost_usd") or 0.0
            ) + float(projected_edge_usd)
        self._save()

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._state)
