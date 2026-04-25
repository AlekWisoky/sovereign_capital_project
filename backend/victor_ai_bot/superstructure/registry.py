from __future__ import annotations

from ..pathing import canonical_data_dir

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .types import AgentHandle, AgentState, GroupName, RoleName, StateTransition
from ..caq_kds.bus import BUS

_SAFE_META_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_STORAGE_EXCEPTIONS = (OSError, TypeError, ValueError)
_SAFE_BUS_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


class AgentRegistry:
    """AGR registry + state machine logging (add-only).

    Notes:
      - This is not the RL agent layer; it's an *organizational* control plane.
      - Used for: coordination, negotiation, capital allocation, oversight.
      - Purely additive: can be disabled.
    """

    def __init__(self, *, data_dir: str, chain: str):
        root = canonical_data_dir(str(data_dir or '') or 'backend/data')
        self.chain = str(chain or "global")
        self._path = os.path.join(root, "superstructure", f"agent_state_{self.chain}.jsonl")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._agents: Dict[str, AgentHandle] = {}
        self._transitions: List[StateTransition] = []
        self._meta_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_action": "",
        }
        self._storage_state: Dict[str, Any] = {
            "ok": True,
            "path": self._path,
            "last_error_code": "",
            "last_error": "",
            "last_action": "",
            "last_write_ts": 0.0,
        }
        self._bus_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_action": "",
            "last_publish_ts": 0.0,
        }

    def upsert(self, handle: AgentHandle) -> None:
        self._agents[handle.agent_id] = handle

    def get(self, agent_id: str) -> Optional[AgentHandle]:
        return self._agents.get(str(agent_id))

    def list(self) -> List[Dict[str, Any]]:
        return [a.as_dict() for a in self._agents.values()]

    def state(self) -> Dict[str, Any]:
        return {
            "meta_update": dict(self._meta_state),
            "storage": dict(self._storage_state),
            "bus_publish": dict(self._bus_state),
            "degraded": not (bool(self._meta_state.get("ok", True)) and bool(self._storage_state.get("ok", True)) and bool(self._bus_state.get("ok", True))),
        }

    def set_suspended(self, agent_id: str, suspended: bool, *, reason: str = "") -> bool:
        a = self._agents.get(str(agent_id))
        if not a:
            return False
        a.suspended = bool(suspended)
        prev = a.state
        a.state = AgentState.SUSPENDED if a.suspended else AgentState.IDLE
        self._log_transition(a, prev, a.state, reason=reason or ("pause" if suspended else "resume"))
        return True

    def transition(self, agent_id: str, new_state: AgentState, *, reason: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
        a = self._agents.get(str(agent_id))
        if not a:
            return
        if a.suspended:
            # hard safety: suspended agents stay suspended
            return
        prev = a.state
        a.state = new_state
        self._safe_update_meta(a, meta)
        self._log_transition(a, prev, new_state, reason=reason, meta=meta)

    def error(self, agent_id: str, err: str, *, meta: Optional[Dict[str, Any]] = None) -> None:
        a = self._agents.get(str(agent_id))
        if not a:
            return
        a.last_error = str(err or "")[:400]
        prev = a.state
        a.state = AgentState.ERROR
        self._safe_update_meta(a, meta)
        self._log_transition(a, prev, a.state, reason=str(err or "error"), meta=meta)

    def snapshot(self, *, limit_transitions: int = 200) -> Dict[str, Any]:
        return {
            "ok": True,
            "chain": self.chain,
            "agents": self.list(),
            "transitions": [t.__dict__ for t in self._transitions[-int(limit_transitions):]],
            "runtime": self.state(),
        }

    def _safe_update_meta(self, a: AgentHandle, meta: Optional[Dict[str, Any]]) -> None:
        if not meta:
            self._mark_bucket(self._meta_state, ok=True, last_action="meta_skip")
            return
        try:
            payload = dict(meta)
            a.meta.update(payload)
            self._mark_bucket(self._meta_state, ok=True, last_action="meta_update")
        except _SAFE_META_EXCEPTIONS as exc:
            self._mark_bucket(self._meta_state, ok=False, code="registry_meta_invalid", error=str(exc), last_action="meta_update")

    def _log_transition(self, a: AgentHandle, prev: AgentState, new: AgentState, *, reason: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
        ts = float(time.time())
        a.last_transition_ts = ts
        tr = StateTransition(
            ts=ts,
            agent_id=a.agent_id,
            group=str(a.group.value),
            role=str(a.role.value),
            prev=str(prev.value),
            new=str(new.value),
            reason=str(reason or ""),
            meta=self._safe_meta_payload(meta),
        )
        self._transitions.append(tr)
        self._append_transition(tr)
        self._publish_transition(tr)

    def _safe_meta_payload(self, meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not meta:
            return {}
        try:
            return dict(meta)
        except _SAFE_META_EXCEPTIONS:
            return {}

    def _append_transition(self, tr: StateTransition) -> None:
        try:
            line = json.dumps(tr.__dict__, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
            fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            try:
                self._write_all(fd, line)
            finally:
                os.close(fd)
            self._mark_bucket(self._storage_state, ok=True, last_action="append_transition", last_write_ts=float(time.time()))
        except _SAFE_STORAGE_EXCEPTIONS as exc:
            self._mark_bucket(self._storage_state, ok=False, code="registry_transition_write_failed", error=str(exc), last_action="append_transition")

    def _publish_transition(self, tr: StateTransition) -> None:
        try:
            BUS.update("org", {"last_transition": tr.__dict__})
            self._mark_bucket(self._bus_state, ok=True, last_action="publish_transition", last_publish_ts=float(time.time()))
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bucket(self._bus_state, ok=False, code="registry_bus_publish_failed", error=str(exc), last_action="publish_transition")

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            n = os.write(fd, view[written:])
            if n <= 0:
                raise OSError("short_write")
            written += n

    @staticmethod
    def _mark_bucket(bucket: Dict[str, Any], *, ok: bool, code: str = "", error: str = "", last_action: str = "", last_write_ts: float | None = None, last_publish_ts: float | None = None) -> None:
        bucket["ok"] = bool(ok)
        bucket["last_error_code"] = str(code or "")
        bucket["last_error"] = str(error or "")[:400]
        if last_action:
            bucket["last_action"] = str(last_action)
        if last_write_ts is not None:
            bucket["last_write_ts"] = float(last_write_ts)
        if last_publish_ts is not None:
            bucket["last_publish_ts"] = float(last_publish_ts)


def default_registry(*, data_dir: str, chain: str) -> AgentRegistry:
    reg = AgentRegistry(data_dir=data_dir, chain=chain)
    # Seed with required roles/groups (minimal set).
    reg.upsert(AgentHandle(agent_id="coordinator", group=GroupName.EXECUTION, role=RoleName.COORDINATOR))
    reg.upsert(AgentHandle(agent_id="negotiator", group=GroupName.EXECUTION, role=RoleName.NEGOTIATOR))
    reg.upsert(AgentHandle(agent_id="observer", group=GroupName.KNOWLEDGE, role=RoleName.OBSERVER))
    reg.upsert(AgentHandle(agent_id="strategy_initiator", group=GroupName.STRATEGY, role=RoleName.INITIATOR))
    reg.upsert(AgentHandle(agent_id="arb_initiator", group=GroupName.ARBITRAGE, role=RoleName.INITIATOR))
    reg.upsert(AgentHandle(agent_id="mev_initiator", group=GroupName.MEV, role=RoleName.INITIATOR))
    reg.upsert(AgentHandle(agent_id="risk_executor", group=GroupName.RISK, role=RoleName.EXECUTOR))
    reg.upsert(AgentHandle(agent_id="trade_executor", group=GroupName.EXECUTION, role=RoleName.EXECUTOR))
    return reg
