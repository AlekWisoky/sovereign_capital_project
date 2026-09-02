from __future__ import annotations

import hashlib
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(value) for value in parts)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def execution_id(
    *,
    decision_id: str,
    correlation_id: str,
    tx_hash: str = "",
    route_id: str = "",
    existing: str = "",
) -> str:
    """Return or deterministically derive the canonical execution identity."""
    current = _text(existing)
    if current:
        return current
    return _stable_id(
        "execution",
        decision_id,
        correlation_id,
        tx_hash,
        route_id,
    )


def outcome_id(
    *,
    decision_id: str,
    correlation_id: str,
    transaction_id: str = "",
    tx_hash: str = "",
    existing: str = "",
) -> str:
    """Return or deterministically derive the canonical settled-outcome identity."""
    current = _text(existing)
    if current:
        return current
    return _stable_id(
        "outcome",
        decision_id,
        correlation_id,
        transaction_id,
        tx_hash,
    )
