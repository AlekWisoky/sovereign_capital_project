from __future__ import annotations

import os
import threading
import json
from typing import Any, Dict, Tuple

from victor_ai_bot.runtime_services.phase7_context_store import Phase7ContextStore


_REQUIRED = ("decision_id", "correlation_id", "execution_id", "settlement_id", "action")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


class CanonicalSettlementIndex:
    """Cached lookup of receipt_settlement transaction IDs.

    The canonical TreasuryLedger remains the source of settlement identity.
    The index rescans only when the ledger file mtime changes, avoiding a disk
    scan for every outcome while never synthesizing a settlement identifier.
    """

    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(
            str(data_dir or "backend/data"),
            "treasury",
            f"ledger_transactions_{str(chain or 'default')}.jsonl",
        )
        self._lock = threading.Lock()
        self._mtime_ns = -1
        self._by_receipt: Dict[str, str] = {}

    def _refresh(self) -> None:
        try:
            mtime_ns = int(os.stat(self.path).st_mtime_ns)
        except OSError:
            self._mtime_ns = -1
            return
        if mtime_ns == self._mtime_ns:
            return
        index: Dict[str, str] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(row, dict):
                        continue
                    if _text(row.get("tx_type")) != "receipt_settlement":
                        continue
                    receipt_id = _text(row.get("receipt_id"))
                    transaction_id = _text(row.get("transaction_id"))
                    if receipt_id and transaction_id:
                        index[receipt_id.lower()] = transaction_id
        except OSError:
            index = {}
        self._by_receipt = index
        self._mtime_ns = mtime_ns

    def resolve(self, tx_hash: str) -> str:
        key = _text(tx_hash).lower()
        if not key:
            return ""
        with self._lock:
            self._refresh()
            return str(self._by_receipt.get(key) or "")


def prepare_real_outcome_for_omar(
    outcome: Any,
    *,
    store: Phase7ContextStore,
    settlement_index: CanonicalSettlementIndex | None = None,
) -> Tuple[bool, list[str]]:
    """Attach Phase 7 context and fail closed unless exact lineage is present.

    Settlement identity is resolved only from the canonical ``receipt_settlement``
    ledger transaction. It is never derived from tx_hash or a PnL row id.
    """
    context = getattr(outcome, "context", None)
    if not isinstance(context, dict):
        return False, ["missing_outcome_context"]

    tx_hash = _text(getattr(outcome, "tx_hash", ""))
    phase7 = _mapping(context.get("phase7_context"))
    if not phase7 and tx_hash:
        phase7 = store.get(tx_hash)
    if phase7:
        context["phase7_context"] = dict(phase7)

    phase7_decision = _mapping(phase7.get("decision"))
    phase7_execution = _mapping(phase7.get("execution"))
    lineage = _mapping(context.get("lineage"))
    for key in ("decision_id", "correlation_id", "execution_id", "action"):
        if not _text(lineage.get(key)):
            lineage[key] = _text(
                phase7_decision.get(key)
                or phase7_execution.get(key)
                or context.get(key)
            )

    if not _text(lineage.get("settlement_id")) and settlement_index is not None:
        lineage["settlement_id"] = settlement_index.resolve(tx_hash)

    context["lineage"] = lineage
    missing = [key for key in _REQUIRED if not _text(lineage.get(key))]
    if missing:
        context["learning_gate"] = {
            "eligible": False,
            "reason_codes": [f"missing_{key}" for key in missing],
        }
        return False, [f"missing_{key}" for key in missing]

    context["learning_gate"] = {"eligible": True, "reason_codes": []}
    return True, []
