from __future__ import annotations

"""Canonical decision context for the production decision/execution/learning path.

The context is transport-oriented: it carries intent and authority through the
lifecycle without granting any field execution authority by itself.
Governance remains the final execution gate.
"""

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Mapping, Optional


def _decimal_string(value: Any) -> str:
    """Return a canonical finite decimal string without binary-float amounts."""
    if value in (None, ""):
        return "0"
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("amount must be a finite decimal") from exc
    if not value.is_finite():
        raise ValueError("amount must be finite")
    return format(value, "f")


@dataclass(frozen=True)
class WealthObjective:
    target_amount: str = "0"
    currency: str = ""
    timeframe_seconds: int = 0
    source: str = "human"

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_amount", _decimal_string(self.target_amount))
        object.__setattr__(self, "currency", str(self.currency or "").upper())
        object.__setattr__(self, "timeframe_seconds", max(0, int(self.timeframe_seconds or 0)))


@dataclass(frozen=True)
class HumanIntent:
    instruction: str = ""
    aggressiveness: str = "normal"
    risk_multiplier: float = 1.0
    source: str = "human"

    def __post_init__(self) -> None:
        object.__setattr__(self, "aggressiveness", str(self.aggressiveness or "normal").strip().lower())
        object.__setattr__(self, "risk_multiplier", max(0.0, min(1.0, float(self.risk_multiplier))))


@dataclass(frozen=True)
class AIRecommendation:
    action: str = ""
    rationale: str = ""
    confidence: float = 0.0
    model: str = ""
    source: str = "ai"

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))


@dataclass(frozen=True)
class CapitalAuthority:
    """Actual capital authority snapshot; amounts remain exact decimal strings."""

    deployable_bankroll_wei: str = "0"
    internal_prime_wei: str = "0"
    external_borrow_capacity_wei: str = "0"
    family_allocations_wei: Dict[str, str] = field(default_factory=dict)
    authority_source: str = "capital_engine"
    as_of_block: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "deployable_bankroll_wei", _decimal_string(self.deployable_bankroll_wei))
        object.__setattr__(self, "internal_prime_wei", _decimal_string(self.internal_prime_wei))
        object.__setattr__(self, "external_borrow_capacity_wei", _decimal_string(self.external_borrow_capacity_wei))
        object.__setattr__(self, "family_allocations_wei", {
            str(k): _decimal_string(v) for k, v in dict(self.family_allocations_wei or {}).items()
        })
        object.__setattr__(self, "as_of_block", max(0, int(self.as_of_block or 0)))


@dataclass(frozen=True)
class LatencyContext:
    observed_at_ns: int = 0
    market_data_age_ms: float = 0.0
    decision_latency_ms: float = 0.0
    execution_deadline_ms: float = 0.0
    gas_mode: str = "standard"
    source: str = "latency_engine"


@dataclass(frozen=True)
class CanonicalDecisionContext:
    """Immutable identity + intent + authority carried through one trade lifecycle."""

    decision_id: str
    correlation_id: str
    human_intent: HumanIntent = field(default_factory=HumanIntent)
    wealth_objective: WealthObjective = field(default_factory=WealthObjective)
    ai_recommendation: AIRecommendation = field(default_factory=AIRecommendation)
    capital_authority: CapitalAuthority = field(default_factory=CapitalAuthority)
    latency: LatencyContext = field(default_factory=LatencyContext)
    strategy_family: str = ""
    opportunity_id: str = ""
    route_id: str = ""
    created_at_ns: int = 0
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not str(self.decision_id).strip():
            raise ValueError("decision_id is required")
        if not str(self.correlation_id).strip():
            raise ValueError("correlation_id is required")
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "correlation_id", str(self.correlation_id))
        object.__setattr__(self, "strategy_family", str(self.strategy_family or ""))
        object.__setattr__(self, "opportunity_id", str(self.opportunity_id or ""))
        object.__setattr__(self, "route_id", str(self.route_id or ""))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def lineage(self) -> Dict[str, str]:
        return {
            "decision_id": self.decision_id,
            "correlation_id": self.correlation_id,
            "opportunity_id": self.opportunity_id,
            "route_id": self.route_id,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CanonicalDecisionContext":
        raw = dict(data or {})
        human = dict(raw.get("human_intent") or {})
        wealth = dict(raw.get("wealth_objective") or {})
        ai = dict(raw.get("ai_recommendation") or {})
        capital = dict(raw.get("capital_authority") or {})
        latency = dict(raw.get("latency") or raw.get("latency_context") or {})
        return cls(
            decision_id=str(raw.get("decision_id") or ""),
            correlation_id=str(raw.get("correlation_id") or ""),
            human_intent=HumanIntent(**{k: human[k] for k in human if k in HumanIntent.__dataclass_fields__}),
            wealth_objective=WealthObjective(**{k: wealth[k] for k in wealth if k in WealthObjective.__dataclass_fields__}),
            ai_recommendation=AIRecommendation(**{k: ai[k] for k in ai if k in AIRecommendation.__dataclass_fields__}),
            capital_authority=CapitalAuthority(**{k: capital[k] for k in capital if k in CapitalAuthority.__dataclass_fields__}),
            latency=LatencyContext(**{k: latency[k] for k in latency if k in LatencyContext.__dataclass_fields__}),
            strategy_family=str(raw.get("strategy_family") or ""),
            opportunity_id=str(raw.get("opportunity_id") or ""),
            route_id=str(raw.get("route_id") or ""),
            created_at_ns=max(0, int(raw.get("created_at_ns") or 0)),
            schema_version=max(1, int(raw.get("schema_version") or 1)),
        )


def capital_authority_from_engine_state(state: Optional[Mapping[str, Any]]) -> CapitalAuthority:
    """Normalize the existing capital_engine_state() contract into canonical context."""
    state_map = dict(state or {})
    engine = dict(state_map.get("capital_engine") or {})
    return CapitalAuthority(
        deployable_bankroll_wei=engine.get("deployable_bankroll_wei", "0"),
        internal_prime_wei=engine.get("internal_prime_wei", engine.get("internal_prime", "0")),
        external_borrow_capacity_wei=engine.get(
            "external_borrow_capacity_wei", engine.get("borrow_capacity_wei", "0")
        ),
        family_allocations_wei=engine.get("family_allocations_wei") or {},
        authority_source=str(engine.get("authority_source") or "capital_engine"),
        as_of_block=int(engine.get("as_of_block") or state_map.get("current_block") or 0),
    )
