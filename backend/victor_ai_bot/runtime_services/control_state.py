from __future__ import annotations

from typing import Any, Dict, Optional


def unavailable_state(
    reason_code: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
    include_reason: bool = True,
    include_error: bool = False,
    include_text: bool = False,
) -> Dict[str, Any]:
    """Canonical unavailable-state payload for read-side/runtime compatibility surfaces.

    Preserves legacy compatibility keys while standardizing explicit status and
    reason_code fields for operator and API consumers.
    """

    payload: Dict[str, Any] = {
        "ok": False,
        "status": "unavailable",
        "reason_code": str(reason_code),
    }
    if include_reason:
        payload["reason"] = str(reason_code)
    if include_error:
        payload["error"] = str(reason_code)
    if include_text:
        payload["text"] = str(reason_code)
    if extra:
        payload.update(dict(extra))
    return payload
