from __future__ import annotations

from ..pathing import canonical_data_dir

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..caq_kds.bus import BUS

_SAFE_NUMERIC_EXCEPTIONS = (TypeError, ValueError)
_SAFE_JSON_EXCEPTIONS = (json.JSONDecodeError, TypeError, ValueError)
_SAFE_IO_EXCEPTIONS = (OSError,)
_SAFE_BUS_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)
_SAFE_REGISTRY_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)
_SAFE_COMMAND_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)
_SAFE_TRANSPARENCY_EXCEPTIONS = _SAFE_IO_EXCEPTIONS + _SAFE_JSON_EXCEPTIONS


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except _SAFE_NUMERIC_EXCEPTIONS:
        return float(default)


@dataclass
class GovernanceHealth:
    ts: float
    power_variance: float
    transparency_score: float
    compliance_score: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ts": float(self.ts),
            "power_variance": float(self.power_variance),
            "transparency_score": float(self.transparency_score),
            "compliance_score": float(self.compliance_score),
        }


@dataclass
class GovernanceState:
    """Governance & Management of Autonomous Organizations (GMAO) overlay.

    Hard constraints:
      - Add-only and non-breaking: never mutates core trading logic.
      - Acts as an overlay that can gate execution and trigger human review.
    """

    enabled: bool = True

    # Trilemma weights
    autonomy_weight: float = 0.65
    decentralization_weight: float = 0.55
    efficiency_weight: float = 0.75

    # Power distribution
    power_decay_rate: float = 0.02
    max_agent_power: float = 0.40
    power_rotation_interval: int = 500

    # Reputation
    reputation_decay_rate: float = 0.01
    reputation_min_threshold: float = 0.30

    # Risk governor thresholds
    risk_threshold_drawdown: float = 0.15
    risk_threshold_volatility: float = 0.30

    # Authority
    risk_human_verified: float = 0.80
    risk_supervised: float = 0.50

    # Loop
    health_interval_s: float = 1.0

    # Runtime flags
    system_cycle: int = 0
    risk_emergency_mode: str = "OFF"
    human_override_required: bool = False
    human_escalation_level: int = 0

    # per-agent governance state
    agent_power: Dict[str, float] = field(default_factory=dict)
    agent_reputation: Dict[str, float] = field(default_factory=dict)
    restricted_agents: Dict[str, str] = field(default_factory=dict)  # agent_id -> reason

    last_health: Optional[GovernanceHealth] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "system_cycle": int(self.system_cycle),
            "risk_emergency_mode": str(self.risk_emergency_mode),
            "human_override_required": bool(self.human_override_required),
            "human_escalation_level": int(self.human_escalation_level),
            "trilemma": {
                "autonomy": float(self.autonomy_weight),
                "decentralization": float(self.decentralization_weight),
                "efficiency": float(self.efficiency_weight),
            },
            "power": {k: float(v) for k, v in (self.agent_power or {}).items()},
            "reputation": {k: float(v) for k, v in (self.agent_reputation or {}).items()},
            "restricted": dict(self.restricted_agents or {}),
            "health": (self.last_health.as_dict() if self.last_health else None),
        }


class GMAOGovernance:
    """Non-breaking governance wrapper.

    Designed to be attached to SuperstructureRuntime.
    """

    def __init__(
        self,
        *,
        data_dir: str,
        chain: str,
        state: GovernanceState,
        registry: Any = None,
        command_center: Any = None,
    ):
        self.chain = str(chain or "global")
        self.root = canonical_data_dir(str(data_dir or '') or 'backend/data')
        os.makedirs(os.path.join(self.root, "superstructure"), exist_ok=True)

        self._state = state
        self._registry = registry
        self._command = command_center

        self._state_path = os.path.join(self.root, "superstructure", f"governance_state_{self.chain}.json")
        self._event_path = os.path.join(self.root, "superstructure", f"governance_events_{self.chain}.jsonl")
        self._metric_path = os.path.join(self.root, "superstructure", f"governance_metrics_{self.chain}.jsonl")
        self._decision_audit_path = os.path.join(self.root, "caq_kds", f"decision_audit_{self.chain}.jsonl")

        self._status: Dict[str, Any] = {
            "state": {
                "path": self._state_path,
                "load": self._new_status(path=self._state_path),
                "save": self._new_status(path=self._state_path),
            },
            "events": {
                "path": self._event_path,
                "append": self._new_status(path=self._event_path),
            },
            "metrics": {
                "path": self._metric_path,
                "append": self._new_status(path=self._metric_path),
            },
            "bus": {
                "snapshot": self._new_status(),
                "publish": self._new_status(),
            },
            "command": self._new_status(),
            "registry": self._new_status(),
            "transparency": self._new_status(path=self._decision_audit_path),
        }

        self._last_health_ts: float = 0.0
        self._load()

    @staticmethod
    def _new_status(*, path: str = "") -> Dict[str, Any]:
        return {
            "ok": True,
            "path": str(path or ""),
            "last_error_code": "",
            "last_error": "",
            "last_ts": 0.0,
        }

    @staticmethod
    def _status_payload(status: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": bool(status.get("ok", True)),
            "path": str(status.get("path", "") or ""),
            "lastErrorCode": str(status.get("last_error_code", "") or ""),
            "lastError": str(status.get("last_error", "") or ""),
            "lastTs": float(status.get("last_ts", 0.0) or 0.0),
        }

    def _set_status(self, bucket: str, field: Optional[str], *, ok: bool, reason_code: str = "", error: str = "") -> None:
        target = self._status.get(bucket)
        if field is not None and isinstance(target, dict):
            target = target.get(field)
        if not isinstance(target, dict):
            return
        target["ok"] = bool(ok)
        target["last_error_code"] = str(reason_code or "")
        target["last_error"] = str(error or "")[:240]
        target["last_ts"] = float(time.time())

    def _is_degraded(self) -> bool:
        for value in self._status.values():
            if isinstance(value, dict):
                if "ok" in value and not bool(value.get("ok", True)):
                    return True
                for sub in value.values():
                    if isinstance(sub, dict) and "ok" in sub and not bool(sub.get("ok", True)):
                        return True
        return False

    def _status_snapshot(self) -> Dict[str, Any]:
        return {
            "state": {
                "path": str(self._state_path),
                "load": self._status_payload(self._status["state"]["load"]),
                "save": self._status_payload(self._status["state"]["save"]),
            },
            "events": {
                "path": str(self._event_path),
                "append": self._status_payload(self._status["events"]["append"]),
            },
            "metrics": {
                "path": str(self._metric_path),
                "append": self._status_payload(self._status["metrics"]["append"]),
            },
            "bus": {
                "snapshot": self._status_payload(self._status["bus"]["snapshot"]),
                "publish": self._status_payload(self._status["bus"]["publish"]),
            },
            "command": self._status_payload(self._status["command"]),
            "registry": self._status_payload(self._status["registry"]),
            "transparency": self._status_payload(self._status["transparency"]),
            "degraded": bool(self._is_degraded()),
        }

    def _write_atomic_json(self, path: str, payload: Dict[str, Any]) -> None:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".gmao-", suffix=".json.tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except _SAFE_IO_EXCEPTIONS:
            try:
                os.unlink(tmp_path)
            except _SAFE_IO_EXCEPTIONS:
                pass
            raise

    def _append_jsonl(self, path: str, payload: Dict[str, Any]) -> None:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        record = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            data = record.encode("utf-8")
            written = 0
            while written < len(data):
                written += os.write(fd, data[written:])
            try:
                os.fsync(fd)
            except _SAFE_IO_EXCEPTIONS:
                pass
        finally:
            os.close(fd)

    def _bus_snapshot(self) -> Dict[str, Any]:
        try:
            snap = BUS.snapshot()
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._set_status("bus", "snapshot", ok=False, reason_code="bus_snapshot_failed", error=str(exc))
            return {}
        self._set_status("bus", "snapshot", ok=True)
        return dict(snap or {}) if isinstance(snap, dict) else {}

    def _publish_bus(self, bucket: str, payload: Dict[str, Any], *, reason_code: str) -> None:
        try:
            BUS.update(str(bucket), dict(payload or {}))
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._set_status("bus", "publish", ok=False, reason_code=str(reason_code), error=str(exc))
            return
        self._set_status("bus", "publish", ok=True)

    def _apply_command_center_guardrails(self) -> None:
        if self._command is None:
            self._set_status("command", None, ok=True)
            return
        try:
            self._command.set_exploration_cap(0.15)
            self._command.set_risk_multiplier(0.50)
            self._command.set_directive({"mode": "Maximize stability mode", "reason": "risk_emergency"}, ttl_s=3600.0)
        except _SAFE_COMMAND_EXCEPTIONS as exc:
            self._set_status(
                "command",
                None,
                ok=False,
                reason_code="command_center_update_failed",
                error=str(exc),
            )
            return
        self._set_status("command", None, ok=True)

    # -----------------
    # Persistence
    # -----------------

    def _load(self) -> None:
        if not os.path.exists(self._state_path):
            self._set_status("state", "load", ok=True)
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as handle:
                d = json.loads(handle.read() or "{}")
            p = d.get("power") or {}
            r = d.get("reputation") or {}
            self._state.agent_power.update({str(k): _safe_float(v) for k, v in p.items()})
            self._state.agent_reputation.update({str(k): _safe_float(v) for k, v in r.items()})
            self._state.restricted_agents.update({str(k): str(v) for k, v in (d.get("restricted") or {}).items()})
            self._state.system_cycle = int(d.get("system_cycle", self._state.system_cycle) or self._state.system_cycle)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._set_status("state", "load", ok=False, reason_code="state_load_invalid_json", error=str(exc))
            return
        except _SAFE_IO_EXCEPTIONS as exc:
            self._set_status("state", "load", ok=False, reason_code="state_load_failed", error=str(exc))
            return
        self._set_status("state", "load", ok=True)

    def _save(self) -> None:
        try:
            self._write_atomic_json(self._state_path, self._state.as_dict())
        except _SAFE_IO_EXCEPTIONS as exc:
            self._set_status("state", "save", ok=False, reason_code="state_save_failed", error=str(exc))
            return
        self._set_status("state", "save", ok=True)

    def _log_event(self, kind: str, payload: Dict[str, Any]) -> None:
        rec = {"ts": float(time.time()), "chain": self.chain, "kind": str(kind), "payload": dict(payload or {})}
        try:
            self._append_jsonl(self._event_path, rec)
        except (_SAFE_IO_EXCEPTIONS + _SAFE_JSON_EXCEPTIONS) as exc:
            self._set_status("events", "append", ok=False, reason_code="events_append_failed", error=str(exc))
            return
        self._set_status("events", "append", ok=True)

    def _log_metric(self, payload: Dict[str, Any]) -> None:
        rec = {"ts": float(time.time()), "chain": self.chain, "metric": dict(payload or {})}
        try:
            self._append_jsonl(self._metric_path, rec)
        except (_SAFE_IO_EXCEPTIONS + _SAFE_JSON_EXCEPTIONS) as exc:
            self._set_status("metrics", "append", ok=False, reason_code="metrics_append_failed", error=str(exc))
            return
        self._set_status("metrics", "append", ok=True)

    # -----------------
    # Trilemma balancer
    # -----------------

    def trilemma_balancer(self) -> None:
        s = float(self._state.autonomy_weight + self._state.decentralization_weight + self._state.efficiency_weight)
        if s > 2.0:
            # Prevent trilemma overload
            self._state.decentralization_weight = float(self._state.decentralization_weight * 0.85)
            self._log_event("trilemma_balancer", {"sum": s, "decentralization_weight": self._state.decentralization_weight})

    # -----------------
    # Power + rotation
    # -----------------

    def get_agent_power(self, agent_id: str) -> float:
        return float(self._state.agent_power.get(str(agent_id), 0.10))

    def set_agent_power(self, agent_id: str, power: float) -> None:
        self._state.agent_power[str(agent_id)] = float(_clip(power, 0.0, float(self._state.max_agent_power)))

    def update_agent_power(self, agent_id: str, performance_score: float) -> float:
        aid = str(agent_id)
        cur = float(self.get_agent_power(aid))
        new = cur + (float(performance_score) * 0.01) - float(self._state.power_decay_rate)
        new = float(_clip(new, 0.0, float(self._state.max_agent_power)))
        self.set_agent_power(aid, new)
        self._log_event("agent_power_update", {"agent_id": aid, "performance_score": float(performance_score), "power": new})
        return new

    def rotate_governance_power(self) -> None:
        if int(self._state.power_rotation_interval) <= 0:
            return
        if int(self._state.system_cycle) % int(self._state.power_rotation_interval) != 0:
            return
        # Redistribute proportionally to reputation (bounded), with a small egalitarian floor.
        reps = {k: float(v) for k, v in (self._state.agent_reputation or {}).items()}
        if not reps:
            return
        s = float(sum(reps.values()) or 0.0)
        if s <= 0.0:
            return
        floor = 0.05
        cap = float(self._state.max_agent_power)
        for aid, rv in reps.items():
            share = float(rv / s)
            p = float(_clip(floor + (cap - floor) * share, 0.0, cap))
            self._state.agent_power[aid] = p
        self._log_event("power_rotation", {"cycle": int(self._state.system_cycle), "agents": len(reps)})

    # -----------------
    # Reputation engine
    # -----------------

    def get_agent_reputation(self, agent_id: str) -> float:
        return float(self._state.agent_reputation.get(str(agent_id), 0.50))

    def set_agent_reputation(self, agent_id: str, rep: float) -> None:
        self._state.agent_reputation[str(agent_id)] = float(_clip(rep, 0.0, 1.0))

    def restrict_agent(self, agent_id: str, *, reason: str) -> None:
        aid = str(agent_id)
        self._state.restricted_agents[aid] = str(reason)[:200]
        if self._registry is not None:
            try:
                self._registry.set_suspended(aid, True, reason=f"governance_restrict:{reason}"[:200])
            except _SAFE_REGISTRY_EXCEPTIONS as exc:
                self._set_status("registry", None, ok=False, reason_code="registry_suspend_failed", error=str(exc))
            else:
                self._set_status("registry", None, ok=True)
        self._log_event("agent_restricted", {"agent_id": aid, "reason": str(reason)})

    def update_agent_reputation(self, agent_id: str, outcome_score: float) -> float:
        aid = str(agent_id)
        cur = float(self.get_agent_reputation(aid))
        new = cur + (float(outcome_score) * 0.05) - float(self._state.reputation_decay_rate)
        new = float(_clip(new, 0.0, 1.0))
        self.set_agent_reputation(aid, new)
        if new < float(self._state.reputation_min_threshold):
            self.restrict_agent(aid, reason="reputation_below_threshold")
            self._log_event("governance_review_flag", {"agent_id": aid, "rep": new})
        self._log_event("agent_reputation_update", {"agent_id": aid, "outcome_score": float(outcome_score), "rep": new})
        return new

    # -----------------
    # Risk governor
    # -----------------

    def _get_system_drawdown(self) -> float:
        snap = self._bus_snapshot()
        rel = (snap.get("reliability") or {}).get("data") or {}
        return _safe_float(rel.get("max_drawdown", 0.0), 0.0)

    def _get_market_volatility(self) -> float:
        # Best-effort: use S_global volatility cluster score if present; else reliability volatility.
        snap = self._bus_snapshot()
        sg = (snap.get("S_global") or {}).get("data") or {}
        if isinstance(sg, dict):
            vol = sg.get("volatility")
            if vol is not None:
                return _safe_float(vol, 0.0)
            vc = sg.get("vol_cluster") or {}
            if isinstance(vc, dict):
                return _safe_float(vc.get("score", 0.0), 0.0)
        rel = (snap.get("reliability") or {}).get("data") or {}
        return _safe_float(rel.get("volatility", 0.0), 0.0)

    def require_human_review(self, *, reason: str = "") -> None:
        self._state.human_override_required = True
        self._state.human_escalation_level = max(1, int(self._state.human_escalation_level or 0))
        self._log_event("human_review_required", {"reason": str(reason)[:200]})

    def risk_governor_monitor(self) -> None:
        dd = float(self._get_system_drawdown())
        vol = float(self._get_market_volatility())
        if (dd > float(self._state.risk_threshold_drawdown)) or (vol > float(self._state.risk_threshold_volatility)):
            if self._state.risk_emergency_mode != "ON":
                self._log_event("risk_emergency_on", {"drawdown": dd, "volatility": vol})
            self._state.risk_emergency_mode = "ON"
            self.require_human_review(reason="risk_governor_triggered")
            self._state.human_escalation_level = max(2, int(self._state.human_escalation_level))
            # Limit autonomy (safe centralization)
            self._apply_command_center_guardrails()
        else:
            if self._state.risk_emergency_mode != "OFF":
                self._log_event("risk_emergency_off", {"drawdown": dd, "volatility": vol})
            self._state.risk_emergency_mode = "OFF"
            self._set_status("command", None, ok=True)

    # -----------------
    # Authority layering
    # -----------------

    def decision_authority_layer(self, decision_risk_level: float) -> str:
        if str(self._state.risk_emergency_mode) == "ON":
            return "HUMAN_FORCED"
        rl = float(_clip(decision_risk_level, 0.0, 1.0))
        if rl > float(self._state.risk_human_verified):
            return "HUMAN_VERIFIED"
        if rl > float(self._state.risk_supervised):
            return "SUPERVISED_AUTONOMOUS"
        return "FULLY_AUTONOMOUS"

    # -----------------
    # Execution wrapper
    # -----------------

    def wrapper_execution(self, *, core_command: str, agent_id: str, risk_level: float, proposal_id: str = "") -> Dict[str, Any]:
        if not bool(self._state.enabled):
            return {"ok": True, "allow": True, "authority": "DISABLED"}

        # Increment cycle first (so rotation uses the new cycle count)
        self._state.system_cycle = int(self._state.system_cycle) + 1

        self.trilemma_balancer()
        self.risk_governor_monitor()
        self.rotate_governance_power()

        auth = self.decision_authority_layer(float(risk_level))

        require_human = auth in {"HUMAN_FORCED", "HUMAN_VERIFIED"}
        if require_human:
            self.require_human_review(reason=f"authority={auth}")

        # HUMAN_FORCED always blocks until human approves.
        allow = auth in {"FULLY_AUTONOMOUS", "SUPERVISED_AUTONOMOUS"}

        self._log_event(
            "governance_wrapper",
            {
                "core_command": str(core_command),
                "agent_id": str(agent_id),
                "proposal_id": str(proposal_id),
                "risk_level": float(risk_level),
                "authority": auth,
                "allow": bool(allow),
            },
        )

        # publish snapshot for dashboards
        self._publish_bus("governance", self._state.as_dict(), reason_code="governance_publish_failed")

        # Persist occasionally
        if int(self._state.system_cycle) % 20 == 0:
            self._save()

        return {
            "ok": True,
            "allow": bool(allow),
            "authority": auth,
            "human_required": bool(require_human),
            "human_override_required": bool(self._state.human_override_required),
            "human_escalation_level": int(self._state.human_escalation_level),
            "risk_emergency_mode": str(self._state.risk_emergency_mode),
        }

    # -----------------
    # Health metrics
    # -----------------

    def _transparency_score(self) -> float:
        # Best-effort explainability index derived from the latest decision audit.
        # If audit is unavailable, return a conservative baseline.
        if not os.path.exists(self._decision_audit_path):
            self._set_status("transparency", None, ok=True)
            return 0.35
        try:
            with open(self._decision_audit_path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - 8192), os.SEEK_SET)
                tail = handle.read().decode("utf-8", errors="ignore").splitlines()
            if not tail:
                self._set_status("transparency", None, ok=True)
                return 0.35
            last = json.loads(tail[-1])
            # fields completeness ratio
            keys = [
                "contributing_features",
                "agent_signal_weights",
                "intrinsic_vs_extrinsic_ratio",
                "risk_adjustment_factor",
                "graph_context_used",
                "confidence_score",
            ]
            present = 0
            for key in keys:
                value = last.get(key)
                if value is None:
                    continue
                if isinstance(value, dict) and len(value) == 0:
                    continue
                if isinstance(value, (int, float)) and float(value) == 0.0 and key != "risk_adjustment_factor":
                    continue
                present += 1
            self._set_status("transparency", None, ok=True)
            return float(_clip(present / float(len(keys) or 1), 0.0, 1.0))
        except _SAFE_TRANSPARENCY_EXCEPTIONS as exc:
            self._set_status("transparency", None, ok=False, reason_code="transparency_read_failed", error=str(exc))
            return 0.35

    def _power_variance(self) -> float:
        vals = [float(v) for v in (self._state.agent_power or {}).values()]
        if len(vals) < 2:
            return 0.0
        m = sum(vals) / float(len(vals))
        return float(sum([(x - m) * (x - m) for x in vals]) / float(len(vals)))

    def _compliance_score(self, *, stability_snapshot: Optional[Dict[str, Any]] = None) -> float:
        # Conservative: derive from org stability monitor if present.
        rej = 0.0
        conf = 0.0
        if isinstance(stability_snapshot, dict):
            sm = stability_snapshot.get("stability") or stability_snapshot
            if isinstance(sm, dict):
                metrics = sm.get("metrics") or {}
                if isinstance(metrics, dict):
                    rej = _safe_float(metrics.get("rejection_rate", 0.0), 0.0)
                    conf = _safe_float(metrics.get("conflict_rate", 0.0), 0.0)
        # compliance is high when conflict+rejection are low.
        score = 1.0 - _clip((rej + conf) / 1.5, 0.0, 1.0)
        return float(_clip(score, 0.0, 1.0))

    def health_check(self, *, stability_snapshot: Optional[Dict[str, Any]] = None) -> GovernanceHealth:
        ts = float(time.time())
        pv = float(self._power_variance())
        tr = float(self._transparency_score())
        cs = float(self._compliance_score(stability_snapshot=stability_snapshot))

        h = GovernanceHealth(ts=ts, power_variance=pv, transparency_score=tr, compliance_score=cs)
        self._state.last_health = h

        # log metrics
        self._log_metric({"PowerVariance": pv, "TransparencyScore": tr, "ComplianceScore": cs})

        # publish for dashboard
        self._publish_bus("governance_health", h.as_dict(), reason_code="governance_health_publish_failed")

        # persist occasionally
        self._save()
        return h

    # -----------------
    # Outcome hooks
    # -----------------

    def on_outcome(self, *, agent_id: str, performance_score: float, outcome_score: float) -> None:
        if not bool(self._state.enabled):
            return
        aid = str(agent_id)
        self.update_agent_power(aid, float(performance_score))
        self.update_agent_reputation(aid, float(outcome_score))
        self._save()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "governance": self._state.as_dict(),
            "storage": self._status_snapshot(),
        }
