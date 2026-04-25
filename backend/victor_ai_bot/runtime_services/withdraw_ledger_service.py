from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Mapping

from ..persistence.repositories.ledger_repository import LedgerRepository
from ..treasury.ledger import LedgerLine, TreasuryLedger

_SAFE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    RuntimeError,
    OSError,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _chain_name(runtime: Any) -> str:
    return str(
        getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or "default"
    )


def _int_like(value: Any, default: int = 0) -> int:
    try:
        return int(str(value or default))
    except _SAFE_EXCEPTIONS:
        return int(default)


def _normalize_amount_payload(payload: Mapping[str, Any]) -> str:
    for key in ("amount_wei", "amount", "amountOut", "amount_in", "amount_in_wei", "min_out"):
        value = payload.get(key)
        if value not in {None, ""}:
            return str(value)
    return "0"


def _metadata(event: str, reason: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    payload_dict = dict(payload or {})
    tx_status = str(
        payload_dict.get("tx_status") or payload_dict.get("status") or payload_dict.get("outcome") or ""
    ).strip()
    tx_hash = str(payload_dict.get("tx_hash") or payload_dict.get("hash") or "").strip()
    return {
        "event": str(event or "withdraw_execute"),
        "source": "withdraw_route",
        "reason": str(reason or ""),
        "reason_code": str(payload_dict.get("reason_code") or payload_dict.get("outcome") or ""),
        "outcome": str(payload_dict.get("outcome") or tx_status or ""),
        "tx_status": tx_status,
        "tx_hash": tx_hash,
        "tx_proof_reason": str(payload_dict.get("tx_proof_reason") or ""),
        "token": str(payload_dict.get("token") or payload_dict.get("token_in") or ""),
        "token_out": str(payload_dict.get("token_out") or payload_dict.get("requested_token_out") or payload_dict.get("token_out_requested") or ""),
        "amount_wei": _normalize_amount_payload(payload_dict),
        "destination": str(payload_dict.get("to") or ""),
        "from_address": str(payload_dict.get("from_address") or payload_dict.get("from") or ""),
        "action_reason": str(payload_dict.get("action_reason") or reason or ""),
        **payload_dict,
    }


def _repo_payload(*, chain: str, event: str, tx_hash: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    ts_ms = int(time.time() * 1000)
    return {
        "transaction_id": f"withdraw-route-{uuid.uuid4().hex}",
        "ts_ms": ts_ms,
        "tx_type": str(event or "withdraw_execute"),
        "chain": str(chain or "default"),
        "receipt_id": str(tx_hash or ""),
        "lines": [
            {
                "account": "control:withdraw_route",
                "asset": "USD",
                "amount": 0.0,
                "family": "",
                "venue": "WITHDRAW",
                "note": str(event or "withdraw_execute"),
            },
            {
                "account": "equity:offset",
                "asset": "USD",
                "amount": 0.0,
                "family": "",
                "venue": "WITHDRAW",
                "note": f"offset:{str(event or 'withdraw_execute')}",
            },
        ],
        "metadata": dict(metadata or {}),
    }


def record_withdraw_lifecycle_event(
    runtime: Any,
    *,
    event: str,
    reason: str,
    payload: Mapping[str, Any],
) -> bool:
    event_name = str(event or "").strip()
    if event_name not in {"withdraw_execute", "convert_withdraw_execute"}:
        return False
    payload_dict = dict(payload or {})
    metadata = _metadata(event_name, str(reason or ""), payload_dict)
    tx_hash = str(metadata.get("tx_hash") or "")
    chain = _chain_name(runtime)
    ledger = getattr(runtime, "_ledger", None)
    repo = getattr(runtime, "_ledger_repo", None)

    if ledger is not None and hasattr(ledger, "append_transaction"):
        try:
            tx = ledger.append_transaction(
                tx_type=event_name,
                chain=chain,
                receipt_id=tx_hash,
                lines=[
                    LedgerLine(
                        account="control:withdraw_route",
                        asset="USD",
                        amount=0.0,
                        venue="WITHDRAW",
                        note=event_name,
                    ),
                    LedgerLine(
                        account="equity:offset",
                        asset="USD",
                        amount=0.0,
                        venue="WITHDRAW",
                        note=f"offset:{event_name}",
                    ),
                ],
                metadata=metadata,
            )
            if repo is not None and hasattr(repo, "append_transaction"):
                try:
                    repo.append_transaction(chain=chain, payload=tx.to_dict())
                except _SAFE_EXCEPTIONS:
                    return False
            return True
        except _SAFE_EXCEPTIONS:
            return False

    if repo is not None and hasattr(repo, "append_transaction"):
        try:
            repo.append_transaction(
                chain=chain,
                payload=_repo_payload(
                    chain=chain,
                    event=event_name,
                    tx_hash=tx_hash,
                    metadata=metadata,
                ),
            )
            return True
        except _SAFE_EXCEPTIONS:
            return False
    return False
