from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Proposal:
    """Proposal object used by the negotiation/capital auction engines.

    Requirements:
      - expected_return: float (bps or % proxy)
      - risk_score: float in [0,1]
      - capital_required: float (raw units; wei or notional proxy)
      - execution_latency: float (seconds; proxy)
      - funding_advantage: float (bps proxy)
      - graph_confidence: float in [0,1]
      - reliability_score: float in [0,1]
    """

    proposal_id: str
    kind: str
    agent_id: str

    expected_return: float
    risk_score: float
    capital_required: float
    execution_latency: float
    funding_advantage: float
    graph_confidence: float
    reliability_score: float

    confidence: float = 0.5
    overlap_keys: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "kind": self.kind,
            "agent_id": self.agent_id,
            "expected_return": float(self.expected_return),
            "risk_score": float(self.risk_score),
            "capital_required": float(self.capital_required),
            "execution_latency": float(self.execution_latency),
            "funding_advantage": float(self.funding_advantage),
            "graph_confidence": float(self.graph_confidence),
            "reliability_score": float(self.reliability_score),
            "confidence": float(self.confidence),
            "overlap_keys": list(self.overlap_keys or []),
            "meta": dict(self.meta or {}),
        }
