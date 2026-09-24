from __future__ import annotations

"""Optional bounded AI research quorum.

The quorum is deliberately downstream of market observation and upstream of
governance evidence. It produces canonical evidence only; it cannot create an
execution decision or mutate capital state.
"""

import asyncio
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Mapping

from .router import AgentDecision, AgentRequest, GovernedAIRouter


RESEARCH_ROLES = (
    "quant",
    "sentiment",
    "macro",
    "adversarial",
    "execution_research",
)


@dataclass(frozen=True)
class CanonicalEvidence:
    evidence_id: str
    decision_id: str
    role: str
    claim: str
    confidence: float
    provenance: Dict[str, Any]
    latency_ms: float
    cost_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchQuorumResult:
    ok: bool
    evidence: List[CanonicalEvidence]
    confidence: float
    total_latency_ms: float
    total_cost_usd: float
    reason_code: str = ""


_ROLE_PROMPTS = {
    "quant": "Assess statistical/microstructure evidence and probability of the stated opportunity.",
    "sentiment": "Assess flow/sentiment evidence only as a timing or conviction overlay.",
    "macro": "Assess regime, gas, funding, and macro conditions that can alter edge persistence.",
    "adversarial": "Try to invalidate the opportunity through competition, stale state, MEV, and failure modes.",
    "execution_research": "Assess route quality, venue depth, latency sensitivity, and execution feasibility.",
}


class AIResearchQuorum:
    def __init__(self, router: GovernedAIRouter, *, max_parallel: int = 5):
        self.router = router
        self.max_parallel = max(1, min(5, int(max_parallel)))

    async def evaluate(
        self,
        *,
        decision_id: str,
        context: Mapping[str, Any],
        roles: Iterable[str] = RESEARCH_ROLES,
        max_latency_ms: float = 1_500.0,
        max_cost_usd: float = 0.10,
    ) -> ResearchQuorumResult:
        selected = [str(r) for r in roles if str(r) in _ROLE_PROMPTS][: self.max_parallel]
        if not selected:
            return ResearchQuorumResult(False, [], 0.0, 0.0, 0.0, "no_research_roles")

        context_text = str(dict(context or {}))
        async def one(role: str) -> AgentDecision:
            return await self.router.infer(
                AgentRequest(
                    agent_id=f"research:{role}",
                    task=f"research:{role}",
                    prompt=f"{_ROLE_PROMPTS[role]}\nDecision={decision_id}\nContext={context_text}",
                    capability="general",
                    max_latency_ms=float(max_latency_ms),
                    max_cost_usd=float(max_cost_usd),
                    metadata={"decision_id": decision_id, "research_role": role},
                )
            )

        decisions: List[AgentDecision] = []
        for start in range(0, len(selected), self.max_parallel):
            decisions.extend(await asyncio.gather(*(one(role) for role in selected[start : start + self.max_parallel])))

        evidence: List[CanonicalEvidence] = []
        for role, decision in zip(selected, decisions):
            if not decision.ok or decision.evidence is None:
                continue
            evidence.append(
                CanonicalEvidence(
                    evidence_id=decision.evidence.evidence_id,
                    decision_id=str(decision_id),
                    role=role,
                    claim=decision.evidence.content,
                    confidence=float(decision.confidence.score),
                    provenance={
                        **dict(decision.evidence.provenance),
                        "research_role": role,
                        "authority": "advisory_evidence_only",
                    },
                    latency_ms=float(decision.latency.elapsed_ms),
                    cost_usd=float(decision.cost.estimated_usd),
                )
            )

        if not evidence:
            return ResearchQuorumResult(
                False,
                [],
                0.0,
                max((d.latency.elapsed_ms for d in decisions), default=0.0),
                sum(d.cost.estimated_usd for d in decisions),
                "research_quorum_unavailable",
            )

        confidence = sum(e.confidence for e in evidence) / float(len(evidence))
        return ResearchQuorumResult(
            True,
            evidence,
            float(max(0.0, min(1.0, confidence))),
            max(e.latency_ms for e in evidence),
            sum(e.cost_usd for e in evidence),
            "ok",
        )
