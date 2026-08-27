from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
import time
from typing import Any, Callable, Dict, Mapping, Optional


_SAFE_EXCEPTIONS = (AttributeError, KeyError, OSError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def canonical_id(prefix: str, payload: Mapping[str, Any]) -> str:
    """Create a deterministic identifier from canonical learning payload data."""
    body = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
    digest = sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class CapitalAuthoritySnapshot:
    """Read-only snapshot of the authority that may fund a decision.

    OMAR can consume this authority but cannot manufacture or override it.
    """

    authority_id: str
    available_wei: int = 0
    allocatable_wei: int = 0
    family_allocatable_wei: Dict[str, int] = field(default_factory=dict)
    status: str = "unknown"
    freshness_class: str = "unknown"
    reason_codes: list[str] = field(default_factory=list)
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionLearningRecord:
    decision_id: str
    correlation_id: str
    action: str
    opp_id: str = ""
    route_id: str = ""
    policy_version: str = ""
    state: Dict[str, Any] = field(default_factory=dict)
    capital_authority: CapitalAuthoritySnapshot = field(
        default_factory=lambda: CapitalAuthoritySnapshot(authority_id="unavailable")
    )
    metadata: Dict[str, Any] = field(default_factory=dict)
    ts_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionLearningRecord:
    decision_id: str
    correlation_id: str
    execution_id: str
    status: str
    action: str
    tx_hash: str = ""
    fill_quantity: float = 0.0
    fill_price: float = 0.0
    slippage_bps: float = 0.0
    gas_wei: int = 0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    ts_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SettledOutcomeRecord:
    decision_id: str
    correlation_id: str
    execution_id: str
    settlement_id: str
    status: str
    realized_pnl_wei: int = 0
    realized_pnl_usd_micro: int = 0
    realized_slippage_bps: float = 0.0
    realized_gas_wei: int = 0
    risk_cost_wei: int = 0
    net_reward_wei: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    ts_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionAttribution:
    decision_id: str
    correlation_id: str
    execution_id: str
    settlement_id: str
    action: str
    attribution_weight: float
    reward_wei: int
    eligible_for_learning: bool
    reason_codes: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OmarRealLearningLoop:
    """Canonical bridge from real execution outcomes into OMAR.

    This class is deliberately authority-preserving: OMAR receives the capital
    authority snapshot and settled execution truth, but never gets a method that
    can authorize capital or bypass governance/execution.
    """

    def __init__(
        self,
        *,
        chain_name: str = "default",
        data_dir: str = "data/superstructure",
        policy_updater: Optional[Callable[[ActionAttribution], Dict[str, Any]]] = None,
        capital_authority_reader: Optional[Callable[[], Mapping[str, Any]]] = None,
    ) -> None:
        self.chain_name = _text(chain_name) or "default"
        self.data_dir = str(data_dir or "data/superstructure")
        os.makedirs(self.data_dir, exist_ok=True)
        self.audit_path = os.path.join(
            self.data_dir, f"omar_real_learning_{self.chain_name}.jsonl"
        )
        self.policy_updater = policy_updater
        self.capital_authority_reader = capital_authority_reader
        self._decisions: Dict[str, DecisionLearningRecord] = {}
        self._executions: Dict[str, ExecutionLearningRecord] = {}
        self._outcomes: Dict[str, SettledOutcomeRecord] = {}
        self.last_update: Dict[str, Any] = {}

    def read_capital_authority(self) -> CapitalAuthoritySnapshot:
        """Read actual authority; absence is explicit and never treated as approval."""
        if self.capital_authority_reader is None:
            return CapitalAuthoritySnapshot(
                authority_id="unavailable",
                status="unavailable",
                freshness_class="unavailable",
                reason_codes=["capital_authority_reader_unavailable"],
                source="omar",
            )
        try:
            raw = _dict(self.capital_authority_reader())
        except _SAFE_EXCEPTIONS as exc:
            return CapitalAuthoritySnapshot(
                authority_id="unavailable",
                status="unavailable",
                freshness_class="unavailable",
                reason_codes=["capital_authority_read_failed", _text(exc)],
                source="omar",
            )
        return CapitalAuthoritySnapshot(
            authority_id=_text(raw.get("authority_id") or raw.get("authorityId"))
            or "unknown",
            available_wei=max(0, int(raw.get("available_wei", raw.get("availableWei", 0)) or 0)),
            allocatable_wei=max(
                0, int(raw.get("allocatable_wei", raw.get("allocatableWei", 0)) or 0)
            ),
            family_allocatable_wei={
                _text(k): max(0, int(v or 0))
                for k, v in _dict(
                    raw.get("family_allocatable_wei", raw.get("familyAllocatableWei"))
                ).items()
                if _text(k)
            },
            status=_text(raw.get("status")) or "unknown",
            freshness_class=_text(raw.get("freshness_class", raw.get("freshnessClass")))
            or "unknown",
            reason_codes=[_text(x) for x in (raw.get("reason_codes", raw.get("reasonCodes")) or []) if _text(x)],
            source=_text(raw.get("source")) or "runtime",
        )

    def record_decision(
        self,
        *,
        decision_id: str,
        correlation_id: str,
        action: str,
        opp_id: str = "",
        route_id: str = "",
        policy_version: str = "",
        state: Optional[Mapping[str, Any]] = None,
        capital_authority: Optional[CapitalAuthoritySnapshot] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> DecisionLearningRecord:
        record = DecisionLearningRecord(
            decision_id=_text(decision_id),
            correlation_id=_text(correlation_id),
            action=_text(action),
            opp_id=_text(opp_id),
            route_id=_text(route_id),
            policy_version=_text(policy_version),
            state=_dict(state),
            capital_authority=capital_authority or self.read_capital_authority(),
            metadata=_dict(metadata),
            ts_ms=int(time.time() * 1000),
        )
        if not record.decision_id or not record.correlation_id:
            raise ValueError("decision_id and correlation_id are required")
        self._decisions[record.decision_id] = record
        self._log("decision", record.to_dict())
        return record

    def bind_execution(
        self,
        *,
        decision_id: str,
        correlation_id: str,
        execution_id: str,
        status: str,
        action: str,
        tx_hash: str = "",
        fill_quantity: float = 0.0,
        fill_price: float = 0.0,
        slippage_bps: float = 0.0,
        gas_wei: int = 0,
        latency_ms: float = 0.0,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ExecutionLearningRecord:
        if decision_id not in self._decisions:
            raise KeyError(f"unknown decision_id: {decision_id}")
        record = ExecutionLearningRecord(
            decision_id=_text(decision_id),
            correlation_id=_text(correlation_id),
            execution_id=_text(execution_id),
            status=_text(status),
            action=_text(action),
            tx_hash=_text(tx_hash),
            fill_quantity=float(fill_quantity or 0.0),
            fill_price=float(fill_price or 0.0),
            slippage_bps=float(slippage_bps or 0.0),
            gas_wei=max(0, int(gas_wei or 0)),
            latency_ms=float(latency_ms or 0.0),
            metadata=_dict(metadata),
            ts_ms=int(time.time() * 1000),
        )
        if not record.execution_id or not record.correlation_id:
            raise ValueError("execution_id and correlation_id are required")
        if record.correlation_id != self._decisions[record.decision_id].correlation_id:
            raise ValueError("correlation_id_mismatch")
        self._executions[record.execution_id] = record
        self._log("execution", record.to_dict())
        return record

    def settle_outcome(
        self,
        *,
        decision_id: str,
        correlation_id: str,
        execution_id: str,
        settlement_id: str,
        status: str,
        realized_pnl_wei: int = 0,
        realized_pnl_usd_micro: int = 0,
        realized_slippage_bps: float = 0.0,
        realized_gas_wei: int = 0,
        risk_cost_wei: int = 0,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ActionAttribution:
        execution = self._executions.get(execution_id)
        if execution is None:
            raise KeyError(f"unknown execution_id: {execution_id}")
        if execution.decision_id != decision_id or execution.correlation_id != correlation_id:
            raise ValueError("execution_identity_mismatch")
        reward = int(realized_pnl_wei or 0) - int(realized_gas_wei or 0) - int(risk_cost_wei or 0)
        outcome = SettledOutcomeRecord(
            decision_id=decision_id,
            correlation_id=correlation_id,
            execution_id=execution_id,
            settlement_id=_text(settlement_id),
            status=_text(status),
            realized_pnl_wei=int(realized_pnl_wei or 0),
            realized_pnl_usd_micro=int(realized_pnl_usd_micro or 0),
            realized_slippage_bps=float(realized_slippage_bps or 0.0),
            realized_gas_wei=max(0, int(realized_gas_wei or 0)),
            risk_cost_wei=max(0, int(risk_cost_wei or 0)),
            net_reward_wei=reward,
            metadata=_dict(metadata),
            ts_ms=int(time.time() * 1000),
        )
        if not outcome.settlement_id:
            raise ValueError("settlement_id is required")
        self._outcomes[outcome.settlement_id] = outcome
        self._log("settled_outcome", outcome.to_dict())

        eligible = outcome.status.lower() in {"settled", "closed", "complete", "completed"}
        reasons = [] if eligible else ["outcome_not_settled"]
        attribution = ActionAttribution(
            decision_id=decision_id,
            correlation_id=correlation_id,
            execution_id=execution_id,
            settlement_id=outcome.settlement_id,
            action=execution.action,
            attribution_weight=1.0,
            reward_wei=reward,
            eligible_for_learning=eligible,
            reason_codes=reasons,
            metadata={"status": outcome.status},
        )
        self._log("action_attribution", attribution.to_dict())
        if eligible and self.policy_updater is not None:
            self.last_update = _dict(self.policy_updater(attribution))
            self._log("policy_update", self.last_update)
        return attribution

    def _log(self, event: str, payload: Mapping[str, Any]) -> None:
        obj = {"event": event, "ts_ms": int(time.time() * 1000), **dict(payload)}
        with open(self.audit_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
