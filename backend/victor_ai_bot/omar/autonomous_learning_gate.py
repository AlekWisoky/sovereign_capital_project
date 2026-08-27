from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .learning_integrity import validate_learning_transition


_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def install_autonomous_learning_gate() -> None:
    """Install the production fail-closed boundary before OMAR can learn."""
    from .runtime import OmarRuntime

    original = getattr(OmarRuntime, "observe_outcome", None)
    if original is None or getattr(original, "_autonomous_learning_gate", False):
        return

    def gated_observe_outcome(self: Any, **kwargs: Any):
        decision_id = str(kwargs.get("decision_id") or "").strip()
        pending = {}
        try:
            pending = dict(getattr(self, "_pending_decisions", {}).get(decision_id) or {})
        except _SAFE:
            pending = {}

        metadata = dict(kwargs.get("metadata") or {}) if isinstance(kwargs.get("metadata"), Mapping) else {}
        settlement = dict(metadata.get("settlement") or {}) if isinstance(metadata.get("settlement"), Mapping) else {}
        lineage = dict(metadata.get("canonical_lineage") or {}) if isinstance(metadata.get("canonical_lineage"), Mapping) else {}

        outcome = dict(settlement)
        outcome.update(
            {
                "status": str(settlement.get("status") or "settled").strip(),
                "source": str(settlement.get("source") or metadata.get("source") or "").strip(),
                "decision_id": str(settlement.get("decision_id") or decision_id).strip(),
                "correlation_id": str(
                    settlement.get("correlation_id") or lineage.get("correlation_id") or ""
                ).strip(),
                "opportunity_id": str(
                    settlement.get("opportunity_id") or pending.get("opportunity_id") or ""
                ).strip(),
                "action": str(settlement.get("action") or pending.get("action") or "").strip(),
                "route_id": str(
                    settlement.get("route_id") or kwargs.get("route_id") or pending.get("route_id") or ""
                ).strip(),
                "outcome_truth_verified": bool(
                    settlement.get(
                        "truth_verified",
                        settlement.get("outcome_truth_verified", kwargs.get("outcome_truth_verified", False)),
                    )
                ),
                "canonical_lineage": {
                    "decision_id": str(lineage.get("decision_id") or decision_id).strip(),
                    "correlation_id": str(lineage.get("correlation_id") or "").strip(),
                },
            }
        )

        gate = validate_learning_transition(pending, outcome, decision_id=decision_id)
        if not gate.allowed:
            try:
                self._log(
                    {
                        "event": "omar_learning_gate_rejected",
                        "decision_id": decision_id,
                        "reason": gate.reason,
                        "gate": gate.to_dict(),
                    }
                )
            except _SAFE:
                pass
            return {
                "ok": False,
                "learned": False,
                "reason": gate.reason,
                "decision_id": decision_id,
            }

        return original(self, **kwargs)

    gated_observe_outcome._autonomous_learning_gate = True
    OmarRuntime.observe_outcome = gated_observe_outcome
