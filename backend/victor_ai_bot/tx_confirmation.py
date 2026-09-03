from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SubmittedTxStatus:
    tx_hash: str
    tx_status: str
    receipt_status: int | None = None
    block_number: int | None = None
    receipt: dict[str, Any] | None = None
    proof_reason: str = ""


def _decode_hex_int(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return int(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            return int(text, 16) if text.startswith("0x") else int(text, 10)
        except (TypeError, ValueError):
            return None
    return None


async def assess_submitted_tx(
    rpc: Any,
    *,
    tx_hash: str,
    send_mode: str,
) -> SubmittedTxStatus:
    """Classify a successfully submitted transaction without blocking on long receipt waits.

    Semantics:
    - mined_success: immediate receipt with status=1
    - mined_reverted: immediate receipt with status=0
    - pending: public send, no receipt yet, but tx is visible by hash
    - sent: private/protected send accepted, no immediate receipt yet
    - receipt_unavailable: public send accepted but read RPC cannot yet prove visibility/receipt
    """

    normalized_send_mode = str(send_mode or "public").strip().lower()
    call = getattr(rpc, "call", None)
    if callable(call):
        receipt_result = await call("eth_getTransactionReceipt", [tx_hash])
        if getattr(receipt_result, "ok", False):
            receipt = getattr(receipt_result, "result", None)
            if isinstance(receipt, Mapping):
                receipt_dict = dict(receipt)
                receipt_status = _decode_hex_int(receipt_dict.get("status"))
                block_number = _decode_hex_int(receipt_dict.get("blockNumber"))
                if receipt_status == 1:
                    return SubmittedTxStatus(
                        tx_hash=tx_hash,
                        tx_status="mined_success",
                        receipt_status=1,
                        block_number=block_number,
                        receipt=receipt_dict,
                        proof_reason="receipt_mined",
                    )
                if receipt_status == 0:
                    return SubmittedTxStatus(
                        tx_hash=tx_hash,
                        tx_status="mined_reverted",
                        receipt_status=0,
                        block_number=block_number,
                        receipt=receipt_dict,
                        proof_reason="receipt_mined",
                    )
                return SubmittedTxStatus(
                    tx_hash=tx_hash,
                    tx_status="receipt_unavailable",
                    block_number=block_number,
                    receipt=receipt_dict,
                    proof_reason="receipt_observed",
                )
            if receipt not in {None, ""}:
                if normalized_send_mode in {"private", "protected_rpc"}:
                    return SubmittedTxStatus(
                        tx_hash=tx_hash, tx_status="sent", proof_reason="receipt_lookup_degraded"
                    )
                return SubmittedTxStatus(
                    tx_hash=tx_hash,
                    tx_status="receipt_unavailable",
                    proof_reason="receipt_lookup_degraded",
                )
        elif normalized_send_mode in {"private", "protected_rpc"}:
            return SubmittedTxStatus(
                tx_hash=tx_hash, tx_status="sent", proof_reason="receipt_lookup_degraded"
            )
        else:
            return SubmittedTxStatus(
                tx_hash=tx_hash,
                tx_status="receipt_unavailable",
                proof_reason="receipt_lookup_degraded",
            )

    if normalized_send_mode in {"private", "protected_rpc"}:
        return SubmittedTxStatus(
            tx_hash=tx_hash, tx_status="sent", proof_reason="private_no_public_receipt"
        )

    get_tx_by_hash = getattr(rpc, "get_tx_by_hash", None)
    if callable(get_tx_by_hash):
        tx = await get_tx_by_hash(tx_hash)
        if isinstance(tx, Mapping):
            return SubmittedTxStatus(
                tx_hash=tx_hash, tx_status="pending", proof_reason="tx_visible"
            )

    return SubmittedTxStatus(
        tx_hash=tx_hash, tx_status="receipt_unavailable", proof_reason="tx_not_visible"
    )
