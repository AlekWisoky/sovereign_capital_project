from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List

from ..rft.ids import make_decision_id, make_replay_event_id, stable_json_hash
from ..rft.schema import ReplayBundle, TopOpportunity
from ..runtime_services.profitability_truth import inspect_profit_after_costs_truth
from ..profitability_projection import profitability_summary_projection
from ..portfolio_optimizer import opportunity_route_ready

_SAFE_CAST_EXCEPTIONS = (TypeError, ValueError)
_SAFE_IO_EXCEPTIONS = (OSError, TypeError, ValueError)
_SAFE_JSON_EXCEPTIONS = (json.JSONDecodeError, TypeError, ValueError)
_SAFE_OPPORTUNITY_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(str(x))
    except _SAFE_CAST_EXCEPTIONS:
        return int(default)


def _summary_rank_key(item: Dict[str, Any]) -> tuple[int, int, int, str]:
    verified = bool(item.get("profit_after_costs_verified", False))
    profit_after = _safe_int(item.get("expected_profit_after_costs_wei") or 0)
    route_ready = bool(item.get("route_ready", False))
    after_gas = _safe_int(item.get("expected_profit_after_gas_usd_micro") or 0)
    if route_ready and verified and profit_after > 0:
        bucket = 0
    elif verified and profit_after > 0:
        bucket = 1
    elif route_ready and verified:
        bucket = 2
    elif verified:
        bucket = 3
    elif route_ready:
        bucket = 4
    else:
        bucket = 5
    return (
        bucket,
        -profit_after,
        -after_gas,
        str(item.get("route_id") or item.get("opportunity_id") or ""),
    )


def _profit_after_costs_info(
    opp: Any,
) -> tuple[int, bool, str, int, Dict[str, Any], Dict[str, Any]]:
    projection = profitability_summary_projection(opp)
    return (
        _safe_int(projection.get("displayProfitAfterCostsWeiInt") or 0),
        bool(projection.get("valid", False)),
        str(projection.get("reason") or "profit_after_costs_unavailable"),
        _safe_int(projection.get("displayExpectedProfitAfterCostsUsdMicro") or 0),
        dict(projection.get("postMutationRevalidation") or {}),
        dict(projection.get("stateContract") or {}),
    )


class ReplayBundleStore:
    """Deterministic, append-safe replay bundle storage.

    Bundles are immutable snapshots of the decision context and execution plan.
    The runtime creates a draft bundle before/at execution time and finalizes it
    once dry-run or receipt data is known.
    """

    def __init__(self, *, data_dir: str, chain: str, chain_id: int):
        self.data_dir = str(data_dir)
        self.chain = str(chain)
        self.chain_id = int(chain_id or 0)
        self.root = os.path.join(self.data_dir, "rft", "replay", self.chain)
        os.makedirs(self.root, exist_ok=True)
        self._tx_index_path = os.path.join(self.root, "tx_index.json")
        self._bundle_storage = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_write_ts": 0,
            "last_load_ts": 0,
            "last_event_id": "",
            "root": self.root,
        }
        self._index_storage = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_write_ts": 0,
            "last_load_ts": 0,
            "last_tx_hash": "",
            "path": self._tx_index_path,
        }

    def _bundle_path(self, event_id: str) -> str:
        return os.path.join(self.root, f"{event_id}.json")

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _record_bundle_status(
        self,
        *,
        ok: bool,
        code: str = "",
        error: str = "",
        event_id: str = "",
        write: bool = False,
        load: bool = False,
    ) -> None:
        self._bundle_storage.update(
            {
                "ok": bool(ok),
                "last_error_code": str(code or ""),
                "last_error": str(error or ""),
            }
        )
        if event_id:
            self._bundle_storage["last_event_id"] = str(event_id)
        if write:
            self._bundle_storage["last_write_ts"] = self._now_ms()
        if load:
            self._bundle_storage["last_load_ts"] = self._now_ms()

    def _record_index_status(
        self,
        *,
        ok: bool,
        code: str = "",
        error: str = "",
        tx_hash: str = "",
        write: bool = False,
        load: bool = False,
    ) -> None:
        self._index_storage.update(
            {
                "ok": bool(ok),
                "last_error_code": str(code or ""),
                "last_error": str(error or ""),
            }
        )
        if tx_hash:
            self._index_storage["last_tx_hash"] = str(tx_hash)
        if write:
            self._index_storage["last_write_ts"] = self._now_ms()
        if load:
            self._index_storage["last_load_ts"] = self._now_ms()

    def state(self) -> Dict[str, Any]:
        return {
            "bundleStorage": dict(self._bundle_storage),
            "txIndex": dict(self._index_storage),
            "degraded": not bool(self._bundle_storage.get("ok", True))
            or not bool(self._index_storage.get("ok", True)),
        }

    def _read_json_dict(self, path: str) -> Dict[str, Any] | None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except FileNotFoundError:
            return None
        except _SAFE_JSON_EXCEPTIONS:
            return None
        except _SAFE_IO_EXCEPTIONS:
            return None
        if isinstance(obj, dict):
            return obj
        return None

    def _atomic_write_json(self, path: str, payload: Dict[str, Any]) -> None:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        tmp_path = f"{path}.tmp-{os.getpid()}-{self._now_ms()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp_path, path)

    def _load_tx_index(self) -> Dict[str, str]:
        try:
            obj = self._read_json_dict(self._tx_index_path)
            if obj is None:
                if os.path.exists(self._tx_index_path):
                    self._record_index_status(
                        ok=False,
                        code="tx_index_invalid",
                        error="tx_index_invalid",
                        load=True,
                    )
                    return {}
                self._record_index_status(ok=True, load=True)
                return {}
            out = {str(k): str(v) for k, v in dict(obj).items()}
            self._record_index_status(ok=True, load=True)
            return out
        except _SAFE_IO_EXCEPTIONS as exc:
            self._record_index_status(
                ok=False,
                code="tx_index_load_failed",
                error=str(exc),
                load=True,
            )
            return {}

    def _save_tx_index(self, tx_index: Dict[str, str]) -> bool:
        try:
            self._atomic_write_json(self._tx_index_path, dict(tx_index or {}))
            self._record_index_status(ok=True, write=True)
            return True
        except _SAFE_IO_EXCEPTIONS as exc:
            self._record_index_status(
                ok=False,
                code="tx_index_save_failed",
                error=str(exc),
                write=True,
            )
            return False

    def list_event_ids(self) -> List[str]:
        ids: List[str] = []
        try:
            for name in sorted(os.listdir(self.root)):
                if name.endswith(".json") and name != "tx_index.json":
                    ids.append(name[:-5])
            self._record_bundle_status(ok=True, load=True)
            return ids
        except FileNotFoundError:
            self._record_bundle_status(ok=True, load=True)
            return []
        except _SAFE_IO_EXCEPTIONS as exc:
            self._record_bundle_status(
                ok=False,
                code="bundle_list_failed",
                error=str(exc),
                load=True,
            )
            return []

    def load(self, event_id: str) -> Dict[str, Any] | None:
        clean_event_id = str(event_id or "")
        path = self._bundle_path(clean_event_id)
        if not os.path.exists(path):
            return None
        try:
            obj = self._read_json_dict(path)
            if obj is None:
                self._record_bundle_status(
                    ok=False,
                    code="bundle_invalid",
                    error="bundle_invalid",
                    event_id=clean_event_id,
                    load=True,
                )
                return None
            self._record_bundle_status(ok=True, event_id=clean_event_id, load=True)
            return obj
        except _SAFE_IO_EXCEPTIONS as exc:
            self._record_bundle_status(
                ok=False,
                code="bundle_load_failed",
                error=str(exc),
                event_id=clean_event_id,
                load=True,
            )
            return None

    def load_by_tx_hash(self, tx_hash: str) -> Dict[str, Any] | None:
        tx = str(tx_hash or "").strip()
        if not tx:
            return None
        event_id = self._load_tx_index().get(tx)
        if not event_id:
            return None
        return self.load(event_id)

    def _write_bundle(self, bundle: Dict[str, Any]) -> Dict[str, Any] | None:
        clean = dict(bundle or {})
        clean["event_hash"] = stable_json_hash(
            {k: v for k, v in clean.items() if k != "event_hash"}
        )
        event_id = str(clean.get("event_id") or "")
        path = self._bundle_path(event_id)
        try:
            self._atomic_write_json(path, clean)
            self._record_bundle_status(ok=True, event_id=event_id, write=True)
        except _SAFE_IO_EXCEPTIONS as exc:
            self._record_bundle_status(
                ok=False,
                code="bundle_write_failed",
                error=str(exc),
                event_id=event_id,
                write=True,
            )
            return None
        tx_hash = str(clean.get("tx_hash") or "")
        if tx_hash:
            index = self._load_tx_index()
            index[tx_hash] = event_id
            self._record_index_status(ok=self._save_tx_index(index), tx_hash=tx_hash)
        return clean

    @staticmethod
    def summarize_opportunities(opps: Iterable[Any], *, limit: int = 20) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for o in list(opps or []):
            try:
                meta = getattr(o, "meta", None) if o is not None else None
                brain = meta.get("brain") if isinstance(meta, dict) else {}
                (
                    profit_after,
                    profit_after_verified,
                    profit_after_reason,
                    profit_after_usd,
                    post_mutation,
                    state_contract,
                ) = _profit_after_costs_info(o)
                route_ready, route_reason, route_reason_codes = opportunity_route_ready(o)
                projection = profitability_summary_projection(o)
                why = (
                    [str((brain or {}).get("reason") or "")][:1]
                    if (brain or {}).get("reason")
                    else []
                )
                profit_reason = f"profitability:{str(profit_after_reason or 'ok')}"
                if profit_reason not in why:
                    why.append(profit_reason)
                if not route_ready:
                    for code in list(route_reason_codes or [route_reason]):
                        text_code = str(code or "").strip()
                        if text_code and text_code not in why:
                            why.append(text_code)
                row = TopOpportunity(
                    opportunity_id=str(getattr(o, "id", "") or ""),
                    route_id=str(getattr(o, "route_id", "") or ""),
                    strategy_id=str(
                        getattr(o, "strategy", "flashloan_atomic") or "flashloan_atomic"
                    ),
                    expected_profit_after_costs_wei=str(int(max(0, profit_after))),
                    expected_profit_after_gas_usd_micro=int(max(0, profit_after_usd)),
                    expected_profit_usd_micro=_safe_int(
                        projection.get("displayExpectedProfitUsdMicro") or 0
                    ),
                    send_mode_hint=str((brain or {}).get("gas_mode") or ""),
                    competition=(
                        "high" if float((brain or {}).get("p_success") or 1.0) < 0.65 else "medium"
                    ),
                    venue_tags=[
                        str(getattr(leg, "dex", ""))
                        for leg in list(getattr(getattr(o, "route", None), "legs", []) or [])
                    ][:4],
                    why=why,
                )
                row = row.model_dump() if hasattr(row, "model_dump") else row.dict()
                row["route_ready"] = bool(route_ready)
                row["profit_after_costs_verified"] = bool(profit_after_verified)
                row["post_mutation_revalidation"] = dict(post_mutation or {})
                row["state_contract"] = dict(state_contract or {})
                items.append(row)
            except _SAFE_OPPORTUNITY_EXCEPTIONS:
                continue
        items.sort(key=_summary_rank_key)
        trimmed = items[: max(1, int(limit or 20))]
        for item in trimmed:
            item.pop("route_ready", None)
            item.pop("profit_after_costs_verified", None)
        return trimmed

    def create_bundle(
        self,
        *,
        block_number: int,
        opportunity_id: str,
        route_id: str,
        mode: str,
        rl_state: str,
        rl_action: int,
        runtime: Dict[str, Any],
        controls: Dict[str, Any],
        wealth_goal: Dict[str, Any],
        opportunities: List[Dict[str, Any]],
        execution: Dict[str, Any],
        tx_hash: str = "",
        status: str = "draft",
        audit_hash: str = "",
    ) -> Dict[str, Any] | None:
        decision_id = make_decision_id(
            chain_id=self.chain_id,
            block_number=int(block_number or 0),
            opportunity_id=str(opportunity_id or ""),
            route_id=str(route_id or ""),
            mode=str(mode or ""),
            rl_state=str(rl_state or ""),
            rl_action=int(rl_action or -1),
        )
        event_id = make_replay_event_id(
            chain_id=self.chain_id,
            block_number=int(block_number or 0),
            opportunity_id=str(opportunity_id or ""),
            route_id=str(route_id or ""),
            decision_id=str(decision_id),
        )
        bundle = ReplayBundle(
            event_id=event_id,
            chain=self.chain,
            chain_id=self.chain_id,
            block_number=int(block_number or 0),
            opportunity_id=str(opportunity_id or ""),
            route_id=str(route_id or ""),
            decision_id=str(decision_id),
            created_at_ms=int(time.time() * 1000),
            status=(
                str(status or "draft")
                if str(status or "draft") in {"draft", "dry_run", "submitted", "settled", "failed"}
                else "draft"
            ),
            audit_hash=str(audit_hash or ""),
            tx_hash=str(tx_hash or ""),
            runtime=dict(runtime or {}),
            controls=dict(controls or {}),
            wealth_goal=dict(wealth_goal or {}),
            opportunities=list(opportunities or []),
            execution=dict(execution or {}),
        ).model_dump()
        return self._write_bundle(bundle)

    def finalize(
        self,
        *,
        tx_hash: str,
        status: str,
        receipt: Dict[str, Any],
        decoded_receipt: Dict[str, Any],
        reward_trace: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        bundle = self.load_by_tx_hash(tx_hash)
        if not bundle:
            return None
        bundle["status"] = str(status or "settled")
        bundle["receipt"] = dict(receipt or {})
        bundle["decoded_receipt"] = dict(decoded_receipt or {})
        bundle["reward_trace"] = dict(reward_trace or {})
        return self._write_bundle(bundle)

    def finalize_dry_run(
        self, *, event_id: str, reward_trace: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        bundle = self.load(event_id)
        if not bundle:
            return None
        bundle["status"] = "dry_run"
        bundle["reward_trace"] = dict(reward_trace or {})
        return self._write_bundle(bundle)
