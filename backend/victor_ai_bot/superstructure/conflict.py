from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .proposals import Proposal


@dataclass
class ConflictDecision:
    ok: bool
    selected_id: str
    suppressed_ids: List[str]
    reason: str
    meta: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "selected_id": str(self.selected_id or ""),
            "suppressed_ids": list(self.suppressed_ids or []),
            "reason": str(self.reason or ""),
            "meta": dict(self.meta or {}),
        }


class ConflictResolver:
    """Conflict resolution logic (Phase 18).

    In practice, negotiation already selects a single proposal.
    This helper formalizes overlap detection for audit and future multi-select.
    """

    @staticmethod
    def overlap(a: Proposal, b: Proposal) -> bool:
        if not a.overlap_keys or not b.overlap_keys:
            return False
        sa = set([str(x) for x in a.overlap_keys])
        sb = set([str(x) for x in b.overlap_keys])
        return len(sa.intersection(sb)) > 0

    def resolve(self, proposals: List[Proposal], scores: Dict[str, float]) -> ConflictDecision:
        props = list(proposals or [])
        if not props:
            return ConflictDecision(ok=False, selected_id="", suppressed_ids=[], reason="no_proposals", meta={})
        props_sorted = sorted(props, key=lambda p: float(scores.get(p.proposal_id, -1e18)), reverse=True)
        selected = props_sorted[0]
        suppressed: List[str] = []
        overlaps: List[Tuple[str, str]] = []
        for p in props_sorted[1:]:
            if self.overlap(selected, p):
                overlaps.append((selected.proposal_id, p.proposal_id))
            suppressed.append(p.proposal_id)
        return ConflictDecision(
            ok=True,
            selected_id=selected.proposal_id,
            suppressed_ids=suppressed,
            reason="selected_highest_score",
            meta={"overlaps": overlaps},
        )
