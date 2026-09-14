from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..jsonsafe import to_json_safe as json_safe
from ..tx_confirmation import assess_submitted_tx
from ..rpc import JsonRpcClient
from ._route_helpers import attach_summary_contract

router = APIRouter(tags=["withdraw"])


def _is_evm_address(value: Any) -> bool:
    text = str(value or "").strip()
    if len(text) != 42 or not text.startswith("0x"):
        return False
    try:
        bytes.fromhex(text[2:])
    except (TypeError, ValueError):
        return False
    return True


def _is_tx_hash(value: Any) -> bool:
    text = str(value or "").strip()
    if len(text) != 66 or not text.startswith("0x"):
        return False
    try:
        bytes.fromhex(text[2:])
    except (TypeError, ValueError):
        return False
    return True


def _quantity(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        if text.startswith(("0x", "0X")):
            return hex(int(text, 16))
        return hex(int(text, 10))
    except (TypeError, ValueError):
        return ""


def _chain_id(value: Any) -> str:
    return _quantity(value)


def _intent_digest(*, chain_id: Any, from_address: str, to: str, data: str, value: Any) -> str:
    canonical = {
        "chainId": _chain_id(chain_id),
        "from": str(from_address).lower(),
        "to": str(to).lower(),
        "data": str(data).lower(),
        "value": _quantity(value),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reject(reason: str, **extra: Any) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": "invalid" if reason.startswith("invalid_") or reason.endswith("_mismatch") else "degraded",
        "reason_code": reason,
        "reason": reason,
        "error": reason,
        **extra,
    }


def _runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


@router.post("/api/withdraw/external/reconcile", dependencies=[Depends(require_admin)])
async def reconcile_external_withdraw(request: Request, payload: Dict[str, Any] = Body(...)):
    allowed = {"intent_id", "tx_hash", "chain_id", "from_address", "to", "data", "value"}
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        return json_safe(_reject("invalid_unknown_request_fields", fields=unexpected))

    tx_hash = str(payload.get("tx_hash", "") or "").strip()
    from_address = str(payload.get("from_address", "") or "").strip()
    to = str(payload.get("to", "") or "").strip()
    data = str(payload.get("data", "") or "").strip()
    value = payload.get("value")
    chain_id = payload.get("chain_id")
    intent_id = str(payload.get("intent_id", "") or "").strip().lower()

    if not _is_tx_hash(tx_hash):
        return json_safe(_reject("invalid_tx_hash"))
    if not _is_evm_address(from_address):
        return json_safe(_reject("invalid_from_address"))
    if not _is_evm_address(to):
        return json_safe(_reject("invalid_destination"))
    if not data.startswith("0x") or len(data) < 4 or len(data) % 2:
        return json_safe(_reject("invalid_tx_data"))
    if not _chain_id(chain_id):
        return json_safe(_reject("invalid_chain_id"))
    if not _quantity(value):
        return json_safe(_reject("invalid_tx_value"))
    if len(intent_id) != 64:
        return json_safe(_reject("invalid_intent_id"))

    expected_intent = _intent_digest(
        chain_id=chain_id,
        from_address=from_address,
        to=to,
        data=data,
        value=value,
    )
    if intent_id != expected_intent:
        return json_safe(_reject("intent_mismatch"))

    runtime = _runtime(request)
    cfg = runtime.cfg
    configured_chain = _chain_id(getattr(cfg.chain, "chain_id", 0))
    if configured_chain != _chain_id(chain_id):
        return json_safe(_reject("chain_mismatch", expected_chain_id=configured_chain))

    configured_executor = str(getattr(cfg.execution, "executor_address", "") or "").lower()
    if not _is_evm_address(configured_executor):
        return json_safe(_reject("invalid_executor_address"))
    if to.lower() != configured_executor:
        return json_safe(_reject("submitted_executor_mismatch", expected=configured_executor, actual=to))

    read_url = runtime.rpc_manager.best_read()
    if not read_url:
        return json_safe(_reject("no_rpc_endpoints"))

    async with JsonRpcClient(read_url, timeout_s=10.0, max_concurrency=10, max_batch=20) as rpc:
        tx = await rpc.get_tx_by_hash(tx_hash)
        if not isinstance(tx, Mapping):
            status = await assess_submitted_tx(rpc, tx_hash=tx_hash, send_mode="public")
            return json_safe({
                "ok": True,
                "status": str(status.tx_status),
                "tx_hash": tx_hash,
                "intent_id": intent_id,
                "settled": False,
                "submission_evidence": True,
                "settlement_truth": False,
                "proof_reason": str(status.proof_reason),
            })

        actual_from = str(tx.get("from", "") or "").lower()
        actual_to = str(tx.get("to", "") or "").lower()
        actual_data = str(tx.get("input", tx.get("data", "")) or "").lower()
        actual_value = _quantity(tx.get("value"))
        actual_chain = _chain_id(tx.get("chainId", chain_id))
        if actual_from != from_address.lower():
            return json_safe(_reject("submitted_sender_mismatch", expected=from_address, actual=actual_from))
        if actual_to != to.lower():
            return json_safe(_reject("submitted_destination_mismatch", expected=to, actual=actual_to))
        if actual_data != data.lower():
            return json_safe(_reject("submitted_calldata_mismatch"))
        if actual_value != _quantity(value):
            return json_safe(_reject("submitted_value_mismatch"))
        if actual_chain != _chain_id(chain_id):
            return json_safe(_reject("submitted_chain_mismatch", expected=chain_id, actual=actual_chain))

        status = await assess_submitted_tx(rpc, tx_hash=tx_hash, send_mode="public")
        receipt_truth = status.tx_status in {"mined_success", "mined_reverted"}
        return json_safe(attach_summary_contract({
            "ok": True,
            "status": str(status.tx_status),
            "tx_hash": tx_hash,
            "intent_id": intent_id,
            "settled": False,
            "submission_evidence": True,
            "settlement_truth": receipt_truth,
            "receipt_status": status.receipt_status,
            "block_number": status.block_number,
            "proof_reason": str(status.proof_reason),
            "canonical_receipt": dict(status.receipt or {}) if receipt_truth else None,
        }, family="withdraw_external_reconciliation", read_model="withdraw_external_reconciliation_v1", runtime=runtime))
