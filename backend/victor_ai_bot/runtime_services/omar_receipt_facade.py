from __future__ import annotations

from typing import Any

from ..omar.lifecycle_bridge import _observe_settled_outcome
from .canonical_settlement_interface import canonical_settled_outcome
from .runtime_receipt_facade import RuntimeReceiptFacade


class OmarReceiptFacade(RuntimeReceiptFacade):
    """Receipt facade with direct, post-persistence OMAR learning integration.

    This is composition through inheritance, not runtime monkey-patching. The
    base receipt lifecycle remains authoritative for settlement accounting; OMAR
    is invoked only after that lifecycle has persisted canonical outcome state.
    """

    def canonical_settled_outcome(self, **kwargs: Any) -> dict[str, Any] | None:
        return canonical_settled_outcome(self, **kwargs)

    def _safe_finalize_receipt_side_effects(self, *args: Any, **kwargs: Any) -> None:
        super()._safe_finalize_receipt_side_effects(*args, **kwargs)
        try:
            pending = kwargs.get("pending")
            tx_hash = str(kwargs.get("tx_hash") or "")
            if not isinstance(pending, dict) or not tx_hash:
                return
            sync = dict(getattr(self, "_last_settlement_sync", {}) or {})
            if not bool(sync.get("ok", False)):
                return
            outcome = self.canonical_settled_outcome(
                tx_hash=tx_hash,
                decision_id=str(pending.get("canonical_decision_id") or ""),
                correlation_id=str(pending.get("correlation_id") or ""),
                opportunity_id=str(pending.get("opportunity_id") or ""),
            )
            if outcome is not None:
                _observe_settled_outcome(self, pending=pending, outcome=outcome)
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            # OMAR is downstream learning; settlement truth is never rolled back
            # or masked because an advisory learning update cannot be recorded.
            return
