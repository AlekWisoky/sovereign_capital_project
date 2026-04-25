from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List


_SAFE_KILL_SWITCH_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class KillSwitchStore:
    def __init__(self, *, data_dir: str, chain: str):
        self.chain = str(chain)
        self._path = os.path.join(data_dir, "governance", f"kill_switch_{self.chain}.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._state = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            return {"metrics": {}, "suppressions": {}, "history": []}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return (
                data
                if isinstance(data, dict)
                else {"metrics": {}, "suppressions": {}, "history": []}
            )
        except _SAFE_KILL_SWITCH_LOAD_EXCEPTIONS:
            return {"metrics": {}, "suppressions": {}, "history": []}

    def _persist(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _key(self, *, family: str, route_family: str, venue: str) -> str:
        return "|".join(
            [str(family or "unknown"), str(route_family or "unknown"), str(venue or "unknown")]
        )

    def observe_outcome(
        self,
        *,
        family: str,
        route_family: str,
        venue: str,
        lane: str,
        ok: bool,
        expected_edge_usd: float,
        realized_edge_usd: float,
        slippage_drift_bps: float,
        stale: bool,
        fee_burn_usd: float,
        rpc_pressure: float,
        chain: str,
    ) -> None:
        key = self._key(family=family, route_family=route_family, venue=venue)
        item = dict((self._state.get("metrics") or {}).get(key) or {})
        item["family"] = family
        item["route_family"] = route_family
        item["venue"] = venue
        item["lane"] = lane
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["failures"] = int(item.get("failures") or 0) + (0 if ok else 1)
        item["stales"] = int(item.get("stales") or 0) + (1 if stale else 0)
        item["fee_burn_usd"] = float(item.get("fee_burn_usd") or 0.0) + float(fee_burn_usd)
        item["realized_slippage_drift_bps_sum"] = float(
            item.get("realized_slippage_drift_bps_sum") or 0.0
        ) + float(slippage_drift_bps)
        item["loss_bucket_usd"] = float(item.get("loss_bucket_usd") or 0.0) + max(
            0.0, float(expected_edge_usd) - float(realized_edge_usd)
        )
        item["rpc_pressure_ema"] = float(
            rpc_pressure
            if "rpc_pressure_ema" not in item
            else (0.35 * float(rpc_pressure) + 0.65 * float(item.get("rpc_pressure_ema") or 0.0))
        )
        self._state.setdefault("metrics", {})[key] = item
        decision = self._derive_decision(item=item, chain=chain)
        if decision["suppressed"]:
            self._state.setdefault("suppressions", {})[key] = decision
        elif key in (self._state.get("suppressions") or {}):
            self._state["suppressions"].pop(key, None)
        hist = list(self._state.get("history") or [])
        hist.append({"ts_ms": int(time.time() * 1000), "key": key, "decision": decision})
        self._state["history"] = hist[-200:]
        self._persist()

    def _derive_decision(self, *, item: Dict[str, Any], chain: str) -> Dict[str, Any]:
        attempts = int(item.get("attempts") or 0)
        failure_rate = float(item.get("failures") or 0) / float(max(1, attempts))
        stale_ratio = float(item.get("stales") or 0) / float(max(1, attempts))
        slippage_drift = float(item.get("realized_slippage_drift_bps_sum") or 0.0) / float(
            max(1, attempts)
        )
        fee_burn = float(item.get("fee_burn_usd") or 0.0)
        rpc_pressure = float(item.get("rpc_pressure_ema") or 0.0)
        loss_bucket = float(item.get("loss_bucket_usd") or 0.0)
        reason_codes: List[str] = []
        if fee_burn >= 40.0:
            reason_codes.append("fee_burn_rate")
        if slippage_drift >= 18.0:
            reason_codes.append("realized_slippage_drift")
        if stale_ratio >= 0.35:
            reason_codes.append("stale_quote_ratio")
        if rpc_pressure >= 0.78:
            reason_codes.append("chain_rpc_degradation")
        if failure_rate >= 0.55:
            reason_codes.append("strategy_failure_mode")
        if loss_bucket >= 35.0:
            reason_codes.append("loss_bucket_depletion")
        scope = "none"
        if reason_codes:
            scope = (
                "family"
                if "strategy_failure_mode" in reason_codes
                or "loss_bucket_depletion" in reason_codes
                else "route_family"
            )
        return {
            "suppressed": bool(reason_codes),
            "reason_codes": reason_codes,
            "scope": scope,
            "chain": str(chain),
            "review_required": bool(reason_codes),
            "reset_required": bool(reason_codes),
        }

    def evaluate(
        self,
        *,
        family: str,
        route_family: str,
        venue: str,
        chain: str,
        drawdown_gate: Dict[str, Any] | None = None,
        endpoint_pressure: float = 0.0,
    ) -> Dict[str, Any]:
        key = self._key(family=family, route_family=route_family, venue=venue)
        suppression = dict((self._state.get("suppressions") or {}).get(key) or {})
        reasons = list(suppression.get("reason_codes") or [])
        if float(endpoint_pressure) >= 0.85:
            reasons.append("chain_rpc_degradation")
        if isinstance(drawdown_gate, dict) and not bool(drawdown_gate.get("allowed", True)):
            reasons.extend(list(drawdown_gate.get("reason_codes") or []))
        return {
            "allowed": not bool(reasons),
            "reason_codes": sorted(set(str(x) for x in reasons)),
            "scope": str(suppression.get("scope") or ("family" if reasons else "none")),
            "review_required": bool(reasons),
            "reset_required": bool(reasons),
        }

    def snapshot(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self._state))
