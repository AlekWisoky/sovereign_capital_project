from __future__ import annotations

from collections import Counter
from typing import Any, MutableMapping


def classify_quote_error(error: Any) -> str:
    """Return a stable, non-sensitive quote failure class for read-only telemetry."""
    if isinstance(error, dict):
        code = error.get("code")
        message = str(error.get("message") or "").lower()
        if code in (-32000, -32005) or "execution reverted" in message or "revert" in message:
            return "rpc_revert"
        if "timeout" in message or "timed out" in message:
            return "rpc_timeout"
        if "rate limit" in message or "too many requests" in message or code in (429, -32016):
            return "rpc_rate_limited"
        if "method not found" in message or code in (-32601,):
            return "rpc_method_unsupported"
        if code is not None:
            return f"rpc_error_{code}"
        return "rpc_error"
    message = str(error or "").lower()
    if "timeout" in message or "timed out" in message:
        return "rpc_timeout"
    if "rate limit" in message or "too many requests" in message:
        return "rpc_rate_limited"
    if not message:
        return "rpc_error_unknown"
    return "rpc_transport_or_provider_error"


def record_quote_failure(diagnostics: MutableMapping[str, Any] | None, reason: str) -> None:
    if diagnostics is None:
        return
    counts = diagnostics.setdefault("failure_reasons", Counter())
    counts[str(reason)] += 1


def record_quote_parse_failure(diagnostics: MutableMapping[str, Any] | None, reason: str) -> None:
    if diagnostics is None:
        return
    counts = diagnostics.setdefault("failure_reasons", Counter())
    counts[str(reason)] += 1
