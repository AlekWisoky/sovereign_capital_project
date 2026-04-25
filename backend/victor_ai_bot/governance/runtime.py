from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from ..outcomes import GovernanceOutcome
from .config import GovernanceConfig
from .intent_schema import TransactionIntent, stable_intent_id
from .pdr import PolicyDecisionRecordLog
from .security_stack import run_security_stack
from .threat_monitor import ThreatMonitor
from .workflow_classifier import classify_workflow_tier
from ..pathing import canonical_data_dir


class GovernanceRuntime:
    """Blockchain Agent Standard Layer.

    This runtime:
    - Generates deterministic TransactionIntent objects
    - Runs security + governance checks
    - Tracks approvals (human/operator)
    - Emits an immutable PDR audit log

    It must never change core execution semantics; it only gates.
    """

    def __init__(self, *, cfg: Optional[GovernanceConfig] = None, data_dir: str = "backend/data"):
        self.cfg = cfg or GovernanceConfig()
        self.data_dir = canonical_data_dir(data_dir or "backend/data")
        self.threat = ThreatMonitor()
        self._intents: Dict[str, TransactionIntent] = {}
        pdr_path = os.path.join(self.data_dir, "governance", "pdr.jsonl")
        self.pdr = PolicyDecisionRecordLog(path=pdr_path)

    def generate_intent(
        self,
        *,
        seed: str,
        agent_id: str,
        strategy_type: str,
        objective: Dict[str, Any],
        parameters: Dict[str, Any],
        expected_edge: float,
        risk_profile: str,
        capital_allocation: float,
        execution_constraints: Dict[str, Any],
        governance_tags: Dict[str, Any],
    ) -> TransactionIntent:
        intent_id = (
            stable_intent_id(seed)
            if bool(self.cfg.deterministic_ids)
            else f"int_{int(time.time()*1e6)}"
        )
        it = TransactionIntent(
            intent_id=str(intent_id),
            agent_id=str(agent_id),
            strategy_type=str(strategy_type),
            objective=dict(objective or {}),
            parameters=dict(parameters or {}),
            expected_edge=float(expected_edge),
            risk_profile=str(risk_profile or "conservative"),
            capital_allocation=float(capital_allocation),
            execution_constraints=dict(execution_constraints or {}),
            governance_tags=dict(governance_tags or {}),
        )
        self._intents[it.intent_id] = it
        return it

    def get_intent(self, intent_id: str) -> Optional[TransactionIntent]:
        return self._intents.get(str(intent_id))

    def approve_intent(self, *, intent_id: str, reviewer: str) -> bool:
        it = self._intents.get(str(intent_id))
        if not it:
            return False
        it.approved = True
        it.approval_ts = int(time.time())
        it.reviewer = str(reviewer or "human")
        return True

    def reject_intent(self, *, intent_id: str, reviewer: str) -> bool:
        it = self._intents.get(str(intent_id))
        if not it:
            return False
        it.approved = False
        it.approval_ts = int(time.time())
        it.reviewer = str(reviewer or "human")
        return True

    def governance_check(
        self,
        *,
        intent: TransactionIntent,
        meta: Dict[str, Any],
        simulation_result: Optional[Dict[str, Any]] = None,
        text_inputs: str = "",
        multi_agent_bundle_detected: bool = False,
    ) -> Dict[str, Any]:
        if not bool(self.cfg.enabled):
            return {"ok": True, "outcome": "approved", "tier": "TIER_2_SIMULATION"}

        tier = classify_workflow_tier(
            intent, multi_agent_bundle_detected=bool(multi_agent_bundle_detected)
        )
        threat = self.threat.update(text_inputs=text_inputs, signals=dict(meta or {}))

        # hard constraints
        rp = str(intent.risk_profile or "conservative").lower()
        if rp == "aggressive" and not bool(simulation_result):
            outcome = "rejected"
            reason = "aggressive_requires_simulation"
            ok = False
            sec = {"ok": False, "reason": reason}
        else:
            sec = run_security_stack(
                intent=intent,
                meta=dict(meta or {}),
                threat=threat,
                simulation_result=simulation_result,
                cfg=self.cfg,
            )
            ok = bool(sec.get("ok"))
            outcome = "approved" if ok else "rejected"
            reason = "ok" if ok else "security_stack_failed"

        # multi-agent tier5 requires human
        if (
            tier == "TIER_5_MULTI_AGENT_COORDINATED"
            and bool(self.cfg.require_human_for_tier5)
            and not bool(intent.approved)
        ):
            outcome = "escalated"
            ok = False
            reason = "tier5_requires_human"

        # record PDR
        try:
            self.pdr.append(
                {
                    "intent_id": str(intent.intent_id),
                    "strategy_type": str(intent.strategy_type),
                    "workflow_tier": str(tier),
                    "risk_profile": str(intent.risk_profile),
                    "decision_factors": dict(meta or {}),
                    "simulation_result": dict(simulation_result or {}),
                    "threat": dict(threat or {}),
                    "governance_outcome": str(outcome),
                    "reviewer": str(intent.reviewer or "agent"),
                    "reason": str(reason),
                }
            )
        except (OSError, TypeError, ValueError):
            pass

        gov = GovernanceOutcome(
            allowed=bool(ok),
            reason_code=str(reason),
            required_scope="",
            review_required=(str(outcome) == "escalated"),
            details={"tier": str(tier), "outcome": str(outcome)},
        )
        return {
            "ok": bool(ok),
            "outcome": str(outcome),
            "reason": str(reason),
            "tier": str(tier),
            "threat": dict(threat or {}),
            "security": dict(sec or {}),
            "governanceOutcome": gov.to_dict(),
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.cfg.enabled),
            "intents": {k: v.to_dict() for k, v in list(self._intents.items())[-200:]},
            "threat": self.threat.snapshot(),
            "pdr_tail": self.pdr.tail(50),
        }
