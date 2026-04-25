from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

from .tx_confirmation import SubmittedTxStatus


def submitted_tx_status_payload(result: SubmittedTxStatus) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"tx_status": str(result.tx_status)}
    if str(result.proof_reason or ""):
        payload["tx_proof_reason"] = str(result.proof_reason)
    if result.receipt_status is not None:
        payload["receipt_status"] = int(result.receipt_status)
    if result.block_number is not None:
        payload["block_number"] = int(result.block_number)
    if result.receipt is not None:
        payload["receipt"] = dict(result.receipt)
    return payload


def aggregate_submission_proof_reason(items: Iterable[Mapping[str, Any]]) -> str:
    normalized_items = [item for item in items if isinstance(item, Mapping)]
    if not normalized_items:
        return ""
    statuses = {str(item.get("tx_status") or "") for item in normalized_items}
    statuses.discard("")
    if len(statuses) != 1:
        return ""
    proofs = {
        str(item.get("tx_proof_reason") or item.get("proof_reason") or "")
        for item in normalized_items
    }
    proofs.discard("")
    if len(proofs) != 1:
        return ""
    return next(iter(proofs))
