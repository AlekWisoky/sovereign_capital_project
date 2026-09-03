from __future__ import annotations

import os
from typing import Any, Mapping

from ..identity import identity_from
from .real_learning import canonical_id

_SAFE = (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _enabled() -> bool:
    return (os.environ.get("VICTOR_ENABLE_OMAR", "") or "").strip() == "1"


def _omar(runtime: Any) -> Any:
    current = getattr(runtime, "_omar", None)
    if current is not None:
        current.bind_runtime(runtime)
        return current
    try:
        from .integration import active_omar_runtime

        current = active_omar_runtime()
        if current is not None:
            current.bind_runtime(runtime)
            runtime._omar = current
            return current
    except _SAFE:
        return None
    return None


def _install_execution_hook() -> None:
    from ..runtime_services.execution_service import ExecutionService

    original = getattr(ExecutionService, "handle_post_execute_bookkeeping", None)
    if original is None or getattr(original, "_omar_real_learning_hook", False):
        return

    async def wrapped(
        self: Any, runtime: Any, opp: Any, result: Any, *, bn: int, latency_ms: int, mode: str
    ) -> None:
        await original(self, runtime, opp, result, bn=bn, latency_ms=latency_ms, mode=mode)
        if not _enabled():
            return
        try:
            omar = _omar(runtime)
            if omar is None or not bool(getattr(omar.cfg, "enabled", False)):
                return
            identity = identity_from(opp)
            if identity is None or not identity.decision_id or not identity.correlation_id:
                return
            execution_id = _text(identity.execution_id) or canonical_id(
                "exec",
                {
                    "decision_id": identity.decision_id,
                    "tx_hash": _text(getattr(result, "tx_hash", "")),
                },
            )
            pending = getattr(runtime, "_pending", {}).get(_text(getattr(result, "tx_hash", "")))
            if isinstance(pending, dict):
                pending["canonical_decision_id"] = identity.decision_id
                pending["correlation_id"] = identity.correlation_id
                pending["execution_id"] = execution_id
                pending.setdefault("canonical_lineage", {}).update(
                    {
                        "decision_id": identity.decision_id,
                        "correlation_id": identity.correlation_id,
                        "execution_id": execution_id,
                    }
                )
                meta = _mapping(getattr(opp, "meta", None))
                if isinstance(meta.get("capital_demand"), dict):
                    pending["capital_demand"] = dict(meta["capital_demand"])
                if isinstance(meta.get("operator_intent_snapshot"), dict):
                    pending["operator_intent"] = dict(meta["operator_intent_snapshot"])
            metadata = _mapping(getattr(result, "plan", None))
            omar.observe_execution(
                decision_id=identity.decision_id,
                correlation_id=identity.correlation_id,
                execution_id=execution_id,
                status="submitted" if bool(getattr(result, "submitted", False)) else "executed",
                action=_text(getattr(getattr(result, "decision", None), "action", "")) or "trade",
                tx_hash=_text(getattr(result, "tx_hash", "")),
                slippage_bps=float(metadata.get("slippage_bps") or 0.0),
                gas_wei=int(metadata.get("gas_cost_wei") or 0),
                latency_ms=float(latency_ms),
                metadata={
                    "source": "production_execution_boundary",
                    "block_number": int(bn),
                    "mode": _text(mode),
                },
            )
        except _SAFE:
            return

    wrapped._omar_real_learning_hook = True
    wrapped._omar_real_learning_original = original
    ExecutionService.handle_post_execute_bookkeeping = wrapped


def _install_settlement_hook() -> None:
    from ..runtime_services.runtime_receipt_facade import RuntimeReceiptFacade

    original = getattr(RuntimeReceiptFacade, "_safe_finalize_receipt_side_effects", None)
    if original is None or getattr(original, "_omar_real_learning_hook", False):
        return

    def wrapped(
        self: Any,
        service: Any,
        *,
        tx_hash: str,
        receipt: Any,
        decoded: Any,
        pending: dict,
        status: int,
        submit_to_receipt_ms: int,
        expected_after: int,
        realized_after: int,
        amount_in: int,
        gas_est_wei: int,
        route_id: str,
        reward_trace: dict,
        capture_lane_pending: str,
        capture_relay_pending: str,
        outcome_truth: dict,
    ) -> None:
        original(
            self,
            service,
            tx_hash=tx_hash,
            receipt=receipt,
            decoded=decoded,
            pending=pending,
            status=status,
            submit_to_receipt_ms=submit_to_receipt_ms,
            expected_after=expected_after,
            realized_after=realized_after,
            amount_in=amount_in,
            gas_est_wei=gas_est_wei,
            route_id=route_id,
            reward_trace=reward_trace,
            capture_lane_pending=capture_lane_pending,
            capture_relay_pending=capture_relay_pending,
            outcome_truth=outcome_truth,
        )
        if not _enabled() or int(status) != 1:
            return
        try:
            omar = _omar(self)
            if omar is None or not bool(getattr(omar.cfg, "enabled", False)):
                return
            identity = identity_from(pending) or identity_from(
                _mapping(pending.get("canonical_lineage"))
            )
            if identity is None or not identity.decision_id or not identity.correlation_id:
                return
            execution_id = _text(identity.execution_id) or canonical_id(
                "exec", {"decision_id": identity.decision_id, "tx_hash": str(tx_hash)}
            )
            settlement_id = _text(identity.settlement_id) or canonical_id(
                "settle", {"execution_id": execution_id, "tx_hash": str(tx_hash)}
            )
            from ..learning.outcome_ledger import CanonicalOutcomeLedger

            ledger = CanonicalOutcomeLedger(
                data_dir=str(getattr(self, "data_dir", "backend/data")),
                chain=str(getattr(getattr(self, "cfg", None).chain, "name", "default")),
                bootstrap_history=10,
            )
            rows = ledger.poll(limit=10)
            row = next((item.to_dict() for item in rows if str(item.tx_hash) == str(tx_hash)), None)
            if not isinstance(row, dict):
                return
            metadata = _mapping(row.get("context"))
            metadata.update(
                {
                    "execution": {
                        "execution_id": execution_id,
                        "status": "settled",
                        "gas_wei": int(max(0, gas_est_wei)),
                    },
                    "outcome": {
                        "settlement_id": settlement_id,
                        "realized_pnl_wei": int(realized_after),
                        "realized_gas_wei": int(max(0, row.get("realizedGasCostWei", 0) or 0)),
                    },
                    "capital_demand": _mapping(pending.get("capital_demand")),
                    "latency_ms": float(submit_to_receipt_ms),
                }
            )
            row.update(
                {
                    "decision_id": identity.decision_id,
                    "correlation_id": identity.correlation_id,
                    "execution_id": execution_id,
                    "settlement_id": settlement_id,
                    "action": _text(pending.get("action")) or "trade",
                    "route_id": str(route_id or row.get("routeId") or ""),
                    "status": "settled",
                    "metadata": metadata,
                    "lineage": {
                        "decision_id": identity.decision_id,
                        "correlation_id": identity.correlation_id,
                        "execution_id": execution_id,
                        "settlement_id": settlement_id,
                    },
                }
            )
            omar.observe_settled_ledger_record(row)
        except _SAFE:
            return

    wrapped._omar_real_learning_hook = True
    wrapped._omar_real_learning_original = original
    RuntimeReceiptFacade._safe_finalize_receipt_side_effects = wrapped


def install_production_learning_hooks() -> None:
    _install_execution_hook()
    _install_settlement_hook()
