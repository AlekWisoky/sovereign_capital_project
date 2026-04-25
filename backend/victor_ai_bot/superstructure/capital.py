from __future__ import annotations

from ..pathing import canonical_data_dir

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .proposals import Proposal
from ..caq_kds.bus import BUS


_SAFE_BID_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_BUS_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)
_SAFE_STORAGE_EXCEPTIONS = (OSError,)
_SAFE_JSON_EXCEPTIONS = (TypeError, ValueError)
_SAFE_LAST_EXCEPTIONS = (AttributeError, TypeError, ValueError)


@dataclass
class CapitalAllocation:
    ok: bool
    total_capital: float
    allocations: Dict[str, float] = field(default_factory=dict)
    bids: Dict[str, float] = field(default_factory=dict)
    fragmentation_index: float = 0.0
    ts: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "total_capital": float(self.total_capital),
            "allocations": {k: float(v) for k, v in (self.allocations or {}).items()},
            "bids": {k: float(v) for k, v in (self.bids or {}).items()},
            "fragmentation_index": float(self.fragmentation_index),
            "ts": float(self.ts or 0.0),
        }


class CapitalAuctionEngine:
    """Capital auction engine (Phase 15).

    Conservative defaults:
      - capital is allocated proportionally to bid strength
      - per-task allocation is capped by max_fraction_per_task
    """

    def __init__(self, *, max_fraction_per_task: float = 0.60, data_dir: Optional[str] = None, chain: str = "global"):
        self.max_fraction_per_task = float(max(0.05, min(0.95, float(max_fraction_per_task))))
        self.chain = str(chain or "global")
        self.root = canonical_data_dir(str(data_dir or '') or 'backend/data')
        self._path = os.path.join(self.root, "superstructure", f"capital_{self.chain}.jsonl")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._last: CapitalAllocation = CapitalAllocation(ok=True, total_capital=0.0, ts=time.time())
        self._bid_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_proposal_id": "",
            "last_field": "",
            "last_ts": 0.0,
        }
        self._storage_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "path": self._path,
            "last_write_ts": 0.0,
        }
        self._bus_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_action": "",
            "last_ts": 0.0,
        }
        self._snapshot_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_ts": 0.0,
        }

    def _mark_bucket(self, bucket: Dict[str, Any], *, ok: bool, code: str = "", error: str = "", **extra: Any) -> None:
        bucket["ok"] = bool(ok)
        bucket["last_error_code"] = str(code or "")
        bucket["last_error"] = str(error or "")[:400]
        bucket["last_ts"] = float(time.time())
        for key, value in extra.items():
            bucket[key] = value

    def _runtime_state(self) -> Dict[str, Any]:
        buckets = (self._bid_state, self._storage_state, self._bus_state, self._snapshot_state)
        return {
            "bid": dict(self._bid_state),
            "storage": dict(self._storage_state),
            "bus": dict(self._bus_state),
            "snapshot": dict(self._snapshot_state),
            "degraded": not all(bool(bucket.get("ok", True)) for bucket in buckets),
        }

    def state(self) -> Dict[str, Any]:
        return self._runtime_state()

    def _proposal_id(self, proposal: Proposal) -> str:
        return str(getattr(proposal, "proposal_id", "") or "")

    def _proposal_float(
        self,
        proposal: Proposal,
        field: str,
        *,
        default: float = 0.0,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        error_code: Optional[str] = None,
    ) -> float:
        proposal_id = self._proposal_id(proposal)
        try:
            value = float(getattr(proposal, field, default) or default)
        except _SAFE_BID_EXCEPTIONS as exc:
            self._mark_bucket(
                self._bid_state,
                ok=False,
                code=str(error_code or f"capital_{field}_invalid"),
                error=str(exc),
                last_proposal_id=proposal_id,
                last_field=str(field),
            )
            value = float(default)
        if minimum is not None:
            value = max(float(minimum), value)
        if maximum is not None:
            value = min(float(maximum), value)
        return float(value)

    def _proposal_meta(self, proposal: Proposal) -> Dict[str, Any]:
        proposal_id = self._proposal_id(proposal)
        meta = getattr(proposal, "meta", {}) or {}
        if isinstance(meta, dict):
            return meta
        self._mark_bucket(
            self._bid_state,
            ok=False,
            code="capital_meta_invalid",
            error=f"invalid_meta:{type(meta).__name__}",
            last_proposal_id=proposal_id,
            last_field="meta",
        )
        return {}

    def _meta_float(
        self,
        proposal: Proposal,
        meta: Dict[str, Any],
        field: str,
        *,
        default: float,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> float:
        proposal_id = self._proposal_id(proposal)
        try:
            value = float(meta.get(field, default) or default)
        except _SAFE_BID_EXCEPTIONS as exc:
            self._mark_bucket(
                self._bid_state,
                ok=False,
                code=f"capital_{field}_invalid",
                error=str(exc),
                last_proposal_id=proposal_id,
                last_field=str(field),
            )
            value = float(default)
        if minimum is not None:
            value = max(float(minimum), value)
        if maximum is not None:
            value = min(float(maximum), value)
        return float(value)

    def _bid(self, p: Proposal) -> float:
        # Bid is an internal scoring primitive; not a guarantee of execution.
        # Emphasize expected return and confidence, discounted by risk and boosted by reliability.
        er = self._proposal_float(p, "expected_return", default=0.0, minimum=0.0)
        conf = self._proposal_float(p, "confidence", default=0.0, minimum=0.0, maximum=1.0)
        rel = self._proposal_float(p, "reliability_score", default=0.0, minimum=0.0, maximum=1.0)
        gc = self._proposal_float(p, "graph_confidence", default=0.0, minimum=0.0, maximum=1.0)
        risk = self._proposal_float(p, "risk_score", default=1.0, minimum=0.0, maximum=1.0)

        # Governance overlay (Phase 19): power/reputation adjuster (bounded).
        meta = self._proposal_meta(p)
        gp = self._meta_float(p, meta, "gov_power", default=0.10, minimum=0.0)
        gr = self._meta_float(p, meta, "gov_rep", default=0.50, minimum=0.0, maximum=1.0)
        # reputation: boosts bids modestly when trust is high
        rep_mult = 0.75 + 0.50 * max(0.0, min(1.0, gr))
        # power: kept capped by governance; only a mild multiplier
        pow_mult = 0.85 + 0.30 * max(0.0, min(1.0, gp / 0.40))
        gmult = float(max(0.50, min(1.20, rep_mult * pow_mult)))

        # small positive floor to avoid dead allocations
        return float(gmult * (er * (0.25 + conf) * (0.20 + rel) * (0.20 + gc) * (1.0 - 0.85 * risk) + 1e-6))

    def allocate(self, proposals: List[Proposal], *, total_capital: float) -> CapitalAllocation:
        ts = float(time.time())
        props = list(proposals or [])
        self._mark_bucket(self._bid_state, ok=True, last_proposal_id="", last_field="")
        if not props:
            alloc = CapitalAllocation(ok=False, total_capital=float(total_capital or 0.0), ts=ts)
            self._write(alloc)
            self._last = alloc
            return alloc

        bids: Dict[str, float] = {}
        for p in props:
            bids[self._proposal_id(p)] = max(0.0, float(self._bid(p)))
        s = float(sum(bids.values()) or 0.0)
        if s <= 0.0:
            # fall back to uniform
            for k in bids:
                bids[k] = 1.0
            s = float(sum(bids.values()))

        total = float(max(0.0, float(total_capital or 0.0)))
        cap_each = float(total * self.max_fraction_per_task)
        allocations: Dict[str, float] = {}
        for p in props:
            proposal_id = self._proposal_id(p)
            share = float(bids.get(proposal_id, 0.0) / s)
            want = float(share * total)
            want = min(want, cap_each)
            required = self._proposal_float(
                p,
                "capital_required",
                default=0.0,
                minimum=0.0,
                error_code="capital_required_invalid",
            )
            # never allocate more than requested (raw units)
            want = min(want, required)
            allocations[proposal_id] = float(max(0.0, want))

        # fragmentation = 1 - sum(share^2)
        alloc_sum = float(sum(allocations.values()) or 0.0)
        frag = 0.0
        if alloc_sum > 0.0:
            shares = [float(v / alloc_sum) for v in allocations.values() if v > 0.0]
            frag = float(max(0.0, min(1.0, 1.0 - sum([x * x for x in shares]))))

        out = CapitalAllocation(ok=True, total_capital=total, allocations=allocations, bids=bids, fragmentation_index=frag, ts=ts)
        self._write(out)
        self._last = out
        try:
            BUS.update("capital", out.as_dict())
            self._mark_bucket(self._bus_state, ok=True, last_action="publish")
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bucket(self._bus_state, ok=False, code="capital_publish_failed", error=str(exc), last_action="publish")
        return out

    def _write_all(self, fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            written += os.write(fd, view[written:])

    def _write(self, out: CapitalAllocation) -> None:
        rec = {"ts": float(out.ts or time.time()), "chain": self.chain, "allocation": out.as_dict()}
        try:
            payload = (json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._mark_bucket(self._storage_state, ok=False, code="capital_record_serialize_failed", error=str(exc), path=self._path)
            return
        fd: Optional[int] = None
        try:
            fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            self._write_all(fd, payload)
            self._mark_bucket(self._storage_state, ok=True, path=self._path, last_write_ts=float(out.ts or time.time()))
        except _SAFE_STORAGE_EXCEPTIONS as exc:
            self._mark_bucket(self._storage_state, ok=False, code="capital_record_write_failed", error=str(exc), path=self._path)
        finally:
            if fd is not None:
                os.close(fd)

    def last(self) -> Dict[str, Any]:
        try:
            out = self._last.as_dict()
            self._mark_bucket(self._snapshot_state, ok=True)
            out["runtime"] = self.state()
            return out
        except _SAFE_LAST_EXCEPTIONS as exc:
            self._mark_bucket(self._snapshot_state, ok=False, code="capital_last_failed", error=str(exc))
            return {"ok": False, "error": "capital_last_failed", "runtime": self.state()}
