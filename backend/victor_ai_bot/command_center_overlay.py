"""Sovereign Command Center overlay (additive).

Design goals:
- Local-first, append-only, deterministic audit logging (hash-chained JSONL).
- Operator controls that do NOT rewrite core trading semantics.
- A unified snapshot model for the mobile "Command Center" UI.

This module intentionally avoids touching the core arbitrage engine pathways.
It exposes a thin control layer that the runtime can consult at safe choke points.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

_SAFE_IO_EXCEPTIONS = (OSError,)
_SAFE_JSON_EXCEPTIONS = (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError)


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _storage_status(ok: bool, reason_code: str, *, path: str, detail: str = "") -> Dict[str, Any]:
    return {
        "ok": bool(ok),
        "reasonCode": str(reason_code),
        "path": str(path),
        "detail": str(detail or ""),
    }


@dataclass
class ControlState:
    # "AI proposes. Capital validates. Execution executes."
    # Controls here gate the *capital layer* and execution toggles.
    paused: bool = False
    sandbox_only: bool = False
    allocations_frozen: bool = False
    evolution_frozen: bool = True
    mutation_enabled: bool = False
    governance_enabled: bool = True
    defensive_mode: bool = False
    reduce_exposure_half: bool = False
    # Consumer-friendly control mode overlay.
    # - view_only: no autonomous trading; safe hard stop posture
    # - assist: scanning/explanations live, autonomous execution off
    # - auto: autonomous execution allowed (still bounded by gates)
    control_mode: str = ""
    # Observability toggles (do not affect decisions unless explicitly wired).
    metrics_enabled: bool = True
    latency_profiling_enabled: bool = True
    reward_trace_enabled: bool = True
    chaos_breakers_enabled: bool = True
    rpc_batch_enabled: bool = False
    rft_episode_export_enabled: bool = False

    # Capital engine toggles (additive sizing overlays; safe defaults).
    kelly_enabled: bool = False
    auto_reinvest_enabled: bool = False

    # Optional operator overrides (empty string means "no override").
    force_send_mode: str = ""
    force_gas_mode: str = ""
    brain_mode: str = ""  # "off" | "rl" | "baseline" (best-effort)
    aggression_mode: str = "balanced"  # conservative|balanced|aggressive
    full_system_enabled: bool = False
    # v1 scope lock
    v1_focus: str = "flashloan_atomic"


class AuditStore:
    """Append-only JSONL store with hash chain."""

    def __init__(self, path: str):
        self.path = path
        self._last_hash = "0" * 64
        self._load_status = _storage_status(True, "audit_idle", path=path)
        self._append_status = _storage_status(True, "audit_idle", path=path)
        self._tail_status = _storage_status(True, "audit_idle", path=path)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except _SAFE_IO_EXCEPTIONS as exc:
            self._load_status = _storage_status(
                False,
                "audit_dir_unavailable",
                path=path,
                detail=str(exc),
            )
            return
        self._load_last_hash()

    def _load_last_hash(self) -> None:
        if not os.path.exists(self.path):
            self._load_status = _storage_status(True, "audit_missing", path=self.path)
            return
        bad_lines = 0
        try:
            with open(self.path, "rb") as f:
                for line in f:
                    try:
                        rec = json.loads(line.decode("utf-8"))
                        h = str(rec.get("hash") or "")
                        if len(h) == 64:
                            self._last_hash = h
                    except _SAFE_JSON_EXCEPTIONS:
                        bad_lines += 1
                        continue
        except _SAFE_IO_EXCEPTIONS as exc:
            self._load_status = _storage_status(
                False,
                "audit_read_failed",
                path=self.path,
                detail=str(exc),
            )
            return
        if bad_lines:
            self._load_status = _storage_status(
                False,
                "audit_corrupt_lines_skipped",
                path=self.path,
                detail=f"skipped_lines={bad_lines}",
            )
            return
        self._load_status = _storage_status(True, "audit_loaded", path=self.path)

    def append(
        self, kind: str, payload: Dict[str, Any], *, actor: str = "operator", reason: str = ""
    ) -> Dict[str, Any]:
        ts_ms = int(time.time() * 1000)
        base = {
            "ts_ms": ts_ms,
            "kind": str(kind),
            "actor": str(actor),
            "reason": str(reason),
            "payload": payload,
            "prev_hash": self._last_hash,
        }
        h = _sha256(_canon(base))
        rec = {**base, "hash": h}
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(_canon(rec) + "\n")
        except _SAFE_IO_EXCEPTIONS as exc:
            self._append_status = _storage_status(
                False,
                "audit_append_failed",
                path=self.path,
                detail=str(exc),
            )
            return rec
        self._last_hash = h
        self._append_status = _storage_status(True, "audit_appended", path=self.path)
        return rec

    def tail(self, limit: int = 200) -> List[Dict[str, Any]]:
        limit = max(1, min(2000, int(limit)))
        if not os.path.exists(self.path):
            self._tail_status = _storage_status(True, "audit_missing", path=self.path)
            return []
        out: List[Dict[str, Any]] = []
        bad_lines = 0
        try:
            with open(self.path, "rb") as f:
                lines = f.readlines()[-limit:]
        except _SAFE_IO_EXCEPTIONS as exc:
            self._tail_status = _storage_status(
                False,
                "audit_tail_failed",
                path=self.path,
                detail=str(exc),
            )
            return []
        for ln in lines:
            try:
                out.append(json.loads(ln.decode("utf-8")))
            except _SAFE_JSON_EXCEPTIONS:
                bad_lines += 1
                continue
        if bad_lines:
            self._tail_status = _storage_status(
                False,
                "audit_tail_partial",
                path=self.path,
                detail=f"skipped_lines={bad_lines}",
            )
        else:
            self._tail_status = _storage_status(True, "audit_tail_ok", path=self.path)
        return out

    def state(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "load": dict(self._load_status),
            "append": dict(self._append_status),
            "tail": dict(self._tail_status),
            "degraded": bool(
                not self._load_status.get("ok", True)
                or not self._append_status.get("ok", True)
                or not self._tail_status.get("ok", True)
            ),
        }


class CommandCenterOverlay:
    _BOOL_FIELDS = {
        "paused",
        "sandbox_only",
        "allocations_frozen",
        "evolution_frozen",
        "mutation_enabled",
        "governance_enabled",
        "defensive_mode",
        "reduce_exposure_half",
        "metrics_enabled",
        "latency_profiling_enabled",
        "reward_trace_enabled",
        "chaos_breakers_enabled",
        "rpc_batch_enabled",
        "rft_episode_export_enabled",
        "kelly_enabled",
        "auto_reinvest_enabled",
        "full_system_enabled",
    }
    _VALID_CONTROL_MODES = {"", "view_only", "assist", "auto"}
    _VALID_AGGRESSION_MODES = {"conservative", "balanced", "aggressive"}
    _VALID_FORCE_SEND_MODES = {"", "public", "private", "protected_rpc"}
    _VALID_FORCE_GAS_MODES = {"", "standard", "fast", "instant"}
    _VALID_BRAIN_MODES = {"", "off", "rl", "baseline"}

    def __init__(self, *, data_dir: str, chain: str):
        self.chain = str(chain)
        self.controls_path = os.path.join(data_dir, f"cc_controls_{self.chain}.json")
        self._controls_load_status = _storage_status(True, "controls_idle", path=self.controls_path)
        self._controls_persist_status = _storage_status(
            True, "controls_idle", path=self.controls_path
        )
        self.audit = AuditStore(os.path.join(data_dir, f"cc_audit_{self.chain}.jsonl"))
        self.controls = self._load_controls()

    def _load_controls(self) -> ControlState:
        if not os.path.exists(self.controls_path):
            self._controls_load_status = _storage_status(
                True,
                "controls_missing_defaults_loaded",
                path=self.controls_path,
            )
            return ControlState()
        try:
            with open(self.controls_path, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except _SAFE_IO_EXCEPTIONS as exc:
            self._controls_load_status = _storage_status(
                False,
                "controls_read_failed",
                path=self.controls_path,
                detail=str(exc),
            )
            return ControlState()
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._controls_load_status = _storage_status(
                False,
                "controls_invalid_json",
                path=self.controls_path,
                detail=str(exc),
            )
            return ControlState()
        cs = ControlState()
        for k, v in dict(raw).items():
            if hasattr(cs, k):
                setattr(cs, k, v)
        self._controls_load_status = _storage_status(True, "controls_loaded", path=self.controls_path)
        return cs

    def _persist_controls_state(self, controls: ControlState) -> bool:
        tmp_path = Path(f"{self.controls_path}.tmp")
        target = Path(self.controls_path)
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(asdict(controls), f, indent=2, sort_keys=True)
            os.replace(str(tmp_path), str(target))
        except _SAFE_IO_EXCEPTIONS as exc:
            self._controls_persist_status = _storage_status(
                False,
                "controls_persist_failed",
                path=self.controls_path,
                detail=str(exc),
            )
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except _SAFE_IO_EXCEPTIONS:
                pass
            return False
        self._controls_persist_status = _storage_status(
            True,
            "controls_persisted",
            path=self.controls_path,
        )
        return True

    def persist_controls(self) -> bool:
        return self._persist_controls_state(self.controls)

    @staticmethod
    def _invalid_patch_result(
        reason_code: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "status": "invalid",
            "reason_code": str(reason_code),
            "reason": str(reason_code),
            "error": str(reason_code),
        }
        if details:
            payload["details"] = dict(details)
        return payload

    @staticmethod
    def _coerce_bool(key: str, value: Any) -> Tuple[bool, bool]:
        if isinstance(value, bool):
            return True, value
        if isinstance(value, int) and value in {0, 1}:
            return True, bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True, True
            if normalized in {"false", "0", "no", "off"}:
                return True, False
        return False, False

    def _normalize_patch(self, patch: Mapping[str, Any]) -> Dict[str, Any]:
        errors: List[Dict[str, Any]] = []
        normalized: Dict[str, Any] = {}
        valid_keys = set(ControlState.__dataclass_fields__.keys())

        for key, value in dict(patch or {}).items():
            field = str(key)
            if field not in valid_keys:
                errors.append({"field": field, "reason_code": "unknown_control_field"})
                continue
            if field == "v1_focus":
                errors.append({"field": field, "reason_code": "protected_control_field"})
                continue
            if field in self._BOOL_FIELDS:
                ok, coerced = self._coerce_bool(field, value)
                if not ok:
                    errors.append({
                        "field": field,
                        "reason_code": "invalid_boolean_value",
                        "value": value,
                    })
                    continue
                normalized[field] = coerced
                continue
            if field == "control_mode":
                mode = str(value or "").strip().lower()
                if mode not in self._VALID_CONTROL_MODES:
                    errors.append({
                        "field": field,
                        "reason_code": "invalid_control_mode",
                        "value": value,
                    })
                    continue
                normalized[field] = mode
                continue
            if field == "aggression_mode":
                mode = str(value or "balanced").strip().lower()
                if mode not in self._VALID_AGGRESSION_MODES:
                    errors.append({
                        "field": field,
                        "reason_code": "invalid_aggression_mode",
                        "value": value,
                    })
                    continue
                normalized[field] = mode
                continue
            if field == "force_send_mode":
                mode = str(value or "").strip().lower()
                if mode not in self._VALID_FORCE_SEND_MODES:
                    errors.append({
                        "field": field,
                        "reason_code": "invalid_force_send_mode",
                        "value": value,
                    })
                    continue
                normalized[field] = mode
                continue
            if field == "force_gas_mode":
                mode = str(value or "").strip().lower()
                if mode not in self._VALID_FORCE_GAS_MODES:
                    errors.append({
                        "field": field,
                        "reason_code": "invalid_force_gas_mode",
                        "value": value,
                    })
                    continue
                normalized[field] = mode
                continue
            if field == "brain_mode":
                mode = str(value or "").strip().lower()
                if mode not in self._VALID_BRAIN_MODES:
                    errors.append({
                        "field": field,
                        "reason_code": "invalid_brain_mode",
                        "value": value,
                    })
                    continue
                normalized[field] = mode
                continue
            normalized[field] = value

        if errors:
            return self._invalid_patch_result(
                "invalid_control_patch",
                details={
                    "errors": errors,
                    "accepted_fields": sorted(valid_keys - {"v1_focus"}),
                },
            )
        return {"ok": True, "patch": normalized}

    def state(self) -> Dict[str, Any]:
        controls = {
            "path": self.controls_path,
            "load": dict(self._controls_load_status),
            "persist": dict(self._controls_persist_status),
            "degraded": bool(
                not self._controls_load_status.get("ok", True)
                or not self._controls_persist_status.get("ok", True)
            ),
        }
        audit = self.audit.state()
        return {
            "controls": controls,
            "audit": audit,
            "degraded": bool(controls["degraded"] or audit.get("degraded", False)),
        }

    def set_controls(
        self, patch: Dict[str, Any], *, actor: str = "operator", reason: str = ""
    ) -> Dict[str, Any]:
        before = asdict(self.controls)
        normalized = self._normalize_patch(patch or {})
        if not normalized.get("ok", False):
            return normalized

        candidate = ControlState(**before)
        for key, value in dict(normalized.get("patch") or {}).items():
            setattr(candidate, str(key), value)
        after = asdict(candidate)
        if not self._persist_controls_state(candidate):
            return self._invalid_patch_result(
                "controls_persist_failed",
                details={"storage": self.state(), "before": before},
            )
        self.controls = candidate
        rec = self.audit.append(
            "governance_change", {"before": before, "after": after}, actor=actor, reason=reason
        )
        return {"ok": True, "event": rec, "storage": self.state()}

    def explain(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Operator-facing explanation. Deterministic given snapshot + controls."""
        m = (snapshot.get("metrics") or {}) if isinstance(snapshot, dict) else {}
        ctrl = asdict(self.controls)
        facts = {
            "v1_focus": ctrl.get("v1_focus"),
            "auto_trading": bool(m.get("auto_trading", False)) if isinstance(m, dict) else None,
            "send_mode": m.get("send_mode"),
            "gas_mode": m.get("gas_mode"),
            "paused": ctrl.get("paused"),
            "sandbox_only": ctrl.get("sandbox_only"),
            "allocations_frozen": ctrl.get("allocations_frozen"),
            "evolution_frozen": ctrl.get("evolution_frozen"),
            "mutation_enabled": ctrl.get("mutation_enabled"),
            "storage": self.state(),
        }
        text = (
            "Current regime/edge posture is driven by v1 focus: flashloan atomic arbitrage. "
            "AI proposes opportunities, the capital gate clamps sizing under defensive/probation modes, "
            "and execution follows only if safety rails pass. "
            "If you cannot explain a capital move, disable mutation/evolution and freeze allocations."
        )
        return {"ok": True, "text": text, "facts": facts}
