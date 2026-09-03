from __future__ import annotations

from typing import Any, Dict, Tuple

from victor_ai_bot.runtime_services.phase7_context_store import Phase7ContextStore


_REQUIRED = ("decision_id", "correlation_id", "execution_id", "settlement_id", "action")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def prepare_real_outcome_for_omar(
    outcome: Any,
    *,
    store: Phase7ContextStore,
) -> Tuple[bool, list[str]]:
    """Attach Phase 7 context and fail closed unless exact lineage is present.

    No identifier is synthesized. In particular, settlement_id is never derived
    from tx_hash. A missing identity/action prevents policy updates.
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
    for key in _REQUIRED:
        if not _text(lineage.get(key)):
            lineage[key] = _text(
                phase7_decision.get(key)
                or phase7_execution.get(key)
                or context.get(key)
            )

    # Canonical outcome objects may expose the settlement identity in context;
    # never infer it from the transaction hash or PnL row id.
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
