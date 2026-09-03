from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable


_SAFE_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError, OverflowError)


@dataclass(frozen=True)
class CapitalDemand:
    """Decision-time capital demand/authority snapshot.

    This is deliberately a *constraint* object, not an authorization to borrow
    or execute. Actual capital authority remains with the canonical capital
    engine, internal-prime allocator, treasury governance, and execution gates.
    """

    requested_notional_usd: float = 0.0
    authorized_bankroll_wei: int | None = None
    family_caps_wei: Dict[str, int] = field(default_factory=dict)
    goal_aggressiveness_cap: float = 1.0
    prime_capacity_usd: float = 0.0
    prime_borrowed_usd: float = 0.0
    prime_headroom_ratio: float = 0.0
    prime_state_ready: bool = False
    constrained: bool = False
    reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if value == value and value not in (float("inf"), float("-inf")) else default
    except _SAFE_EXCEPTIONS:
        return default


def _int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return max(0, int(value))
    except _SAFE_EXCEPTIONS:
        return default


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _opportunity_family(opp: Any) -> str:
    meta = _mapping(getattr(opp, "meta", None))
    return str(
        meta.get("strategy_family")
        or meta.get("route_family")
        or getattr(opp, "strategy", "")
        or ""
    ).strip()


def _opportunity_source(opp: Any) -> str:
    meta = _mapping(getattr(opp, "meta", None))
    return str(
        getattr(opp, "loan_source", None)
        or meta.get("loan_source")
        or meta.get("capital_source")
        or ""
    ).strip().lower()


def _opportunity_notional(opp: Any) -> float:
    meta = _mapping(getattr(opp, "meta", None))
    unit = _mapping(meta.get("unit_econ"))
    for value in (
        getattr(opp, "capital_required_usd", None),
        meta.get("capital_required_usd"),
        meta.get("entry_notional_usd"),
        unit.get("entry_notional_usd"),
    ):
        parsed = _float(value)
        if parsed > 0.0:
            return parsed
    micros = _int(unit.get("entry_notional_usd_micro"), 0) or 0
    return float(micros) / 1_000_000.0 if micros > 0 else 0.0


def _goal_cap(wealth_goal_state: Dict[str, Any]) -> float:
    state = _mapping(wealth_goal_state.get("state"))
    value = state.get("aggressivenessCap", wealth_goal_state.get("aggressivenessCap", 1.0))
    return max(0.55, min(1.0, _float(value, 1.0)))


def compose_capital_demand(
    opportunities: Iterable[Any],
    *,
    capital_engine_state: Dict[str, Any] | None,
    internal_prime_state: Dict[str, Any] | None,
    wealth_goal_state: Dict[str, Any] | None = None,
) -> CapitalDemand:
    """Compose the canonical capital constraint used before decision scoring.

    Rules:
    * bankroll authority comes from ``capital_engine_state`` only;
    * internal-prime contributes a dimensionless headroom constraint for
      explicitly prime-backed families, preventing double-counting USD and wei
      authorities;
    * wealth-goal aggressiveness can only shrink the decision budget;
    * missing/corrupt prime truth never fabricates borrowing capacity;
    * no field produced here grants a loan or bypasses governance/execution.
    """

    capital = _mapping(capital_engine_state)
    engine = _mapping(capital.get("capital_engine"))
    prime = _mapping(internal_prime_state)
    goal = _mapping(wealth_goal_state)

    bankroll = _int(engine.get("deployable_bankroll_wei"))
    raw_family_caps = _mapping(engine.get("family_allocations_wei"))
    family_caps = {
        str(k): parsed
        for k, value in raw_family_caps.items()
        if str(k).strip() and (parsed := _int(value)) is not None
    }

    prime_ready = bool(prime.get("stateReady", prime.get("state_ready", False)))
    prime_capacity = max(0.0, _float(prime.get("capacityUsd", prime.get("capacity_usd", 0.0))))
    prime_borrowed = max(0.0, _float(prime.get("borrowedUsd", prime.get("borrowed_usd", 0.0))))
    prime_headroom = max(0.0, prime_capacity - prime_borrowed)
    prime_ratio = (
        max(0.0, min(1.0, prime_headroom / prime_capacity)) if prime_capacity > 0 else 0.0
    )

    aggressiveness_cap = _goal_cap(goal)
    if bankroll is not None:
        authorized_bankroll = int(bankroll * aggressiveness_cap)
    else:
        authorized_bankroll = None

    reasons: list[str] = []
    constrained = False
    if bankroll is not None and aggressiveness_cap < 1.0:
        constrained = True
        reasons.append("wealth_goal_aggressiveness_cap")
    if not prime_ready:
        reasons.append("internal_prime_state_not_ready")

    prime_families: set[str] = set()
    requested = 0.0
    for opp in opportunities:
        requested += _opportunity_notional(opp)
        if _opportunity_source(opp) == "internal_prime":
            family = _opportunity_family(opp)
            if family:
                prime_families.add(family)

    # Scale family caps by the real prime headroom ratio only for families that
    # explicitly request internal-prime capital. This avoids summing two capital
    # authorities that may represent overlapping funds.
    for family in prime_families:
        if family not in family_caps:
            continue
        if not prime_ready or prime_capacity <= 0.0:
            family_caps[family] = 0
            constrained = True
            reasons.append(f"prime_family_blocked:{family}")
        else:
            family_caps[family] = int(family_caps[family] * prime_ratio * aggressiveness_cap)
            if family_caps[family] <= 0:
                constrained = True
                reasons.append(f"prime_family_headroom_zero:{family}")

    # Non-prime family budgets still obey the goal cap, but remain bounded by the
    # capital engine's own allocations. No new capacity is invented here.
    for family in list(family_caps):
        if family not in prime_families and aggressiveness_cap < 1.0:
            family_caps[family] = int(family_caps[family] * aggressiveness_cap)

    if authorized_bankroll is None:
        reasons.append("capital_engine_budget_unavailable")

    return CapitalDemand(
        requested_notional_usd=round(requested, 6),
        authorized_bankroll_wei=authorized_bankroll,
        family_caps_wei=family_caps,
        goal_aggressiveness_cap=round(aggressiveness_cap, 6),
        prime_capacity_usd=round(prime_capacity, 6),
        prime_borrowed_usd=round(prime_borrowed, 6),
        prime_headroom_ratio=round(prime_ratio, 6),
        prime_state_ready=prime_ready,
        constrained=constrained,
        reason_codes=sorted(set(reasons)),
    )
