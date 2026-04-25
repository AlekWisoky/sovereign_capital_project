from __future__ import annotations

from ..pathing import canonical_data_dir

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .proposals import Proposal
from ..caq_kds.bus import BUS

_SAFE_SCORE_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_BUS_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)
_SAFE_IO_EXCEPTIONS = (OSError, TypeError, ValueError)
_SAFE_JSON_EXCEPTIONS = (TypeError, ValueError)


def _write_all(fd: int, payload: str) -> None:
    data = payload.encode("utf-8")
    total = 0
    while total < len(data):
        total += os.write(fd, data[total:])


@dataclass
class NegotiationResult:
    ok: bool
    reason: str
    selected: Optional[Proposal]
    scores: Dict[str, float] = field(default_factory=dict)
    suppressed: List[Dict[str, Any]] = field(default_factory=list)
    ts: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "reason": str(self.reason or ""),
            "selected": (self.selected.as_dict() if self.selected else None),
            "scores": {k: float(v) for k, v in (self.scores or {}).items()},
            "suppressed": list(self.suppressed or []),
            "ts": float(self.ts or 0.0),
        }


class NegotiationEngine:
    """Negotiation protocol engine (Phase 15).

    Implements the required scoring rule:

      Score = expected_return
              - λ1 * risk_score
              - λ2 * latency
              + λ3 * funding_advantage
              + λ4 * reliability_score
              + λ5 * graph_confidence

    Conflict rule:
      - proposals that overlap on any overlap_key are mutually exclusive.
      - coordinator selects the highest scoring proposal; others are suppressed.
    """

    def __init__(
        self,
        *,
        data_dir: str,
        chain: str,
        lambda_risk: float = 1.0,
        lambda_latency: float = 0.05,
        lambda_funding: float = 0.5,
        lambda_reliability: float = 0.6,
        lambda_graph_conf: float = 0.4,
    ):
        self.chain = str(chain or "global")
        self.root = canonical_data_dir(str(data_dir or '') or 'backend/data')
        self._path = os.path.join(self.root, "superstructure", f"negotiation_{self.chain}.jsonl")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

        self.l1 = float(lambda_risk)
        self.l2 = float(lambda_latency)
        self.l3 = float(lambda_funding)
        self.l4 = float(lambda_reliability)
        self.l5 = float(lambda_graph_conf)

        self._last: NegotiationResult = NegotiationResult(ok=True, reason="init", selected=None, ts=time.time())
        self._state: Dict[str, Any] = {
            "score": {"ok": True, "last_error_code": "", "last_error": "", "last_proposal_id": ""},
            "bus": {"ok": True, "last_error_code": "", "last_error": "", "last_reason": ""},
            "storage": {"ok": True, "last_error_code": "", "last_error": "", "path": self._path, "last_write_ts": 0.0},
            "degraded": False,
        }

    def _mark_bucket(self, name: str, *, ok: bool, code: str = "", error: str = "", **extra: Any) -> None:
        bucket = self._state.setdefault(name, {})
        if not isinstance(bucket, dict):
            bucket = {}
            self._state[name] = bucket
        bucket["ok"] = bool(ok)
        bucket["last_error_code"] = str(code or "")
        bucket["last_error"] = str(error or "")
        for key, value in extra.items():
            bucket[key] = value
        self._state["degraded"] = any(not bool((self._state.get(k) or {}).get("ok", True)) for k in ("score", "bus", "storage"))

    def state(self) -> Dict[str, Any]:
        return {
            "score": dict(self._state.get("score") or {}),
            "bus": dict(self._state.get("bus") or {}),
            "storage": dict(self._state.get("storage") or {}),
            "degraded": bool(self._state.get("degraded", False)),
        }

    def _proposal_dict(self, proposal: Proposal) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "proposal_id": str(getattr(proposal, "proposal_id", "") or ""),
            "kind": str(getattr(proposal, "kind", "") or ""),
            "agent_id": str(getattr(proposal, "agent_id", "") or ""),
            "confidence": 0.0,
            "overlap_keys": [],
            "meta": {},
        }
        for key in (
            "expected_return",
            "risk_score",
            "capital_required",
            "execution_latency",
            "funding_advantage",
            "graph_confidence",
            "reliability_score",
            "confidence",
        ):
            try:
                out[key] = float(getattr(proposal, key, 0.0) or 0.0)
            except _SAFE_SCORE_EXCEPTIONS:
                out[key] = 0.0
        try:
            out["overlap_keys"] = [str(x) for x in (getattr(proposal, "overlap_keys", []) or [])]
        except _SAFE_SCORE_EXCEPTIONS:
            out["overlap_keys"] = []
        try:
            meta = getattr(proposal, "meta", {}) or {}
            out["meta"] = dict(meta) if isinstance(meta, dict) else {}
        except _SAFE_SCORE_EXCEPTIONS:
            out["meta"] = {}
        return out

    def _score(self, p: Proposal) -> float:
        return (
            float(p.expected_return)
            - self.l1 * float(p.risk_score)
            - self.l2 * float(p.execution_latency)
            + self.l3 * float(p.funding_advantage)
            + self.l4 * float(p.reliability_score)
            + self.l5 * float(p.graph_confidence)
        )

    def _overlap(self, a: Proposal, b: Proposal) -> bool:
        if not a.overlap_keys or not b.overlap_keys:
            return False
        sa = set([str(x) for x in a.overlap_keys])
        sb = set([str(x) for x in b.overlap_keys])
        return len(sa.intersection(sb)) > 0

    def negotiate(self, proposals: List[Proposal], *, reason: str = "") -> NegotiationResult:
        ts = float(time.time())
        props = list(proposals or [])
        if not props:
            res = NegotiationResult(ok=False, reason="no_proposals", selected=None, ts=ts)
            self._write(res, reason=reason)
            self._last = res
            return res

        # Compute scores.
        scores: Dict[str, float] = {}
        for p in props:
            try:
                scores[p.proposal_id] = float(self._score(p))
                self._mark_bucket("score", ok=True, last_proposal_id=str(getattr(p, "proposal_id", "") or ""))
            except _SAFE_SCORE_EXCEPTIONS as exc:
                scores[p.proposal_id] = -1e9
                self._mark_bucket(
                    "score",
                    ok=False,
                    code="negotiation_score_failed",
                    error=str(exc),
                    last_proposal_id=str(getattr(p, "proposal_id", "") or ""),
                )

        # Select highest score.
        props_sorted = sorted(props, key=lambda p: scores.get(p.proposal_id, -1e9), reverse=True)
        selected = props_sorted[0]

        suppressed: List[Dict[str, Any]] = []
        for p in props_sorted[1:]:
            sup_reason = "not_selected"
            if self._overlap(selected, p):
                sup_reason = "conflict_overlap"
            suppressed.append({"proposal": self._proposal_dict(p), "reason": sup_reason, "score": float(scores.get(p.proposal_id, 0.0))})

        res = NegotiationResult(ok=True, reason="selected", selected=selected, scores=scores, suppressed=suppressed, ts=ts)
        self._write(res, reason=reason)
        self._last = res

        # publish to bus for fusion/xai
        try:
            BUS.update("negotiation", res.as_dict())
            self._mark_bucket("bus", ok=True, last_reason=str(reason or "selected"))
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bucket("bus", ok=False, code="negotiation_publish_failed", error=str(exc), last_reason=str(reason or "selected"))
        return res

    def _write(self, res: NegotiationResult, *, reason: str = "") -> None:
        rec = {
            "ts": float(res.ts or time.time()),
            "chain": self.chain,
            "reason": str(reason or ""),
            "result": res.as_dict(),
        }
        try:
            payload = json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n"
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._mark_bucket("storage", ok=False, code="negotiation_record_serialize_failed", error=str(exc), path=self._path)
            return
        fd: Optional[int] = None
        try:
            fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            _write_all(fd, payload)
            self._mark_bucket("storage", ok=True, path=self._path, last_write_ts=float(res.ts or time.time()))
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mark_bucket("storage", ok=False, code="negotiation_record_write_failed", error=str(exc), path=self._path)
        finally:
            if fd is not None:
                os.close(fd)

    def last(self) -> Dict[str, Any]:
        try:
            out = self._last.as_dict()
            out["runtime"] = self.state()
            return out
        except _SAFE_SCORE_EXCEPTIONS as exc:
            self._mark_bucket("score", ok=False, code="negotiation_last_failed", error=str(exc), last_proposal_id="")
            return {"ok": False, "error": "negotiation_last_failed", "runtime": self.state()}
