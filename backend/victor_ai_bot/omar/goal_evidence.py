from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _first_number(source: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return _float(source[key])
    return 0.0


def _first_text(source: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


@dataclass(frozen=True)
class GoalEvidenceSnapshot:
    """Canonical decision-support snapshot built from authoritative evidence.

    The snapshot is read-only evidence. It does not authorize trades, capital,
    governance, or execution. Missing evidence produces conservative values and
    explicit block reasons rather than invented capacity or performance.
    """

    current_capital: float
    stable_cagr: float
    drawdown: float
    execution_realism: float
    strategy_capacity: float
    prime_utilization_capacity: str
    treasury_reserves: float
    omar_confidence: float
    recommended_goal: float
    next_goal: float
    risk_posture: str
    block_reasons: tuple[str, ...]

    def to_contract(self) -> dict[str, Any]:
        """Return the exact Gate-D recommendation contract and no extra fields."""
        return {
            "Current capital": self.current_capital,
            "Stable CAGR": self.stable_cagr,
            "Drawdown": self.drawdown,
            "Execution realism": self.execution_realism,
            "Strategy capacity": self.strategy_capacity,
            "Prime utilization/capacity": self.prime_utilization_capacity,
            "Treasury reserves": self.treasury_reserves,
            "OMAR confidence": self.omar_confidence,
            "Recommended goal": self.recommended_goal,
            "Next goal": self.next_goal,
            "Risk posture": self.risk_posture,
            "Block reasons": list(self.block_reasons),
        }


def _timestamp(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value) / (1000.0 if float(value) > 10_000_000_000 else 1.0)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _stable_cagr(outcomes: Sequence[Mapping[str, Any]], current_capital: float) -> float:
    if len(outcomes) < 2 or current_capital <= 0:
        return 0.0
    ordered = sorted(
        outcomes, key=lambda row: _timestamp(row.get("ts") or row.get("timestamp")) or 0.0
    )
    start = _first_number(ordered[0], "equity_usd", "equityUsd", "capital_usd", "capitalUsd")
    end = _first_number(ordered[-1], "equity_usd", "equityUsd", "capital_usd", "capitalUsd")
    if start <= 0 or end <= 0:
        pnl = sum(
            _first_number(
                row,
                "realized_pnl_usd",
                "realizedPnlUsd",
                "realized_profit_after_gas_usd",
                "realizedProfitAfterGasUsd",
            )
            for row in ordered
        )
        start = max(0.0, current_capital - pnl)
        end = current_capital
    first_ts = _timestamp(ordered[0].get("ts") or ordered[0].get("timestamp"))
    last_ts = _timestamp(ordered[-1].get("ts") or ordered[-1].get("timestamp"))
    years = (
        ((last_ts - first_ts) / (365.25 * 24.0 * 3600.0))
        if first_ts is not None and last_ts is not None
        else 0.0
    )
    if start <= 0 or end <= 0 or years <= 0.01:
        return 0.0
    return (end / start) ** (1.0 / years) - 1.0


def _drawdown(outcomes: Sequence[Mapping[str, Any]], current_capital: float) -> float:
    if not outcomes:
        return 0.0
    equity = current_capital
    peak = equity
    max_dd = 0.0
    for row in sorted(
        outcomes, key=lambda item: _timestamp(item.get("ts") or item.get("timestamp")) or 0.0
    ):
        explicit = _first_number(row, "equity_usd", "equityUsd")
        if explicit > 0:
            equity = explicit
        else:
            equity += _first_number(
                row,
                "realized_pnl_usd",
                "realizedPnlUsd",
                "realized_profit_after_gas_usd",
                "realizedProfitAfterGasUsd",
            )
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return _clamp(max_dd)


def _execution_realism(outcomes: Sequence[Mapping[str, Any]]) -> float:
    if not outcomes:
        return 0.0
    scores: list[float] = []
    for row in outcomes:
        expected = _first_number(
            row,
            "expected_profit_after_costs_usd",
            "expectedProfitAfterCostsUsd",
            "expected_profit_usd",
        )
        realized = _first_number(
            row,
            "realized_profit_after_gas_usd",
            "realizedProfitAfterGasUsd",
            "realized_pnl_usd",
            "realizedPnlUsd",
        )
        slippage = abs(_first_number(row, "slippage_bps", "slippageBps", "realized_slippage_bps"))
        latency = max(0.0, _first_number(row, "latency_ms", "latencyMs", "submit_to_receipt_ms"))
        cost_evidence = sum(
            key in row
            for key in (
                "realized_gas_cost_wei",
                "realizedGasCostWei",
                "realized_gas_cost_usd_micro",
                "realizedGasCostUsdMicro",
            )
        )
        if expected != 0:
            economics = _clamp(1.0 - abs(realized - expected) / max(abs(expected), 1e-9))
        else:
            economics = 0.5 if realized != 0 else 0.0
        slippage_score = _clamp(1.0 - slippage / 100.0)
        latency_score = _clamp(1.0 - latency / 5000.0)
        completeness = 0.5 + 0.5 * _clamp(cost_evidence / 2.0)
        scores.append(
            economics * 0.45 + slippage_score * 0.2 + latency_score * 0.15 + completeness * 0.2
        )
    return _clamp(sum(scores) / len(scores))


def _prime_contract(prime: Mapping[str, Any]) -> str:
    utilization = _first_number(prime, "utilization", "utilization_ratio", "utilizationRatio")
    capacity = _first_number(prime, "capacity_wei", "capacityWei", "headroom_wei", "headroomWei")
    return f"utilization={_clamp(utilization):.4f};capacity_wei={max(0.0, capacity):.0f}"


def build_goal_evidence_snapshot(
    *,
    settled_outcomes: Iterable[Mapping[str, Any]],
    capital_engine_state: Mapping[str, Any],
    internal_prime_state: Mapping[str, Any] | None = None,
    treasury_state: Mapping[str, Any] | None = None,
    strategy_state: Mapping[str, Any] | None = None,
    omar_state: Mapping[str, Any] | None = None,
    wealth_goal: Mapping[str, Any] | None = None,
) -> GoalEvidenceSnapshot:
    """Build canonical goal evidence from settled returns and runtime authorities."""
    outcomes = [dict(row) for row in settled_outcomes]
    capital = _dict(capital_engine_state)
    prime = _dict(internal_prime_state)
    treasury = _dict(treasury_state)
    strategy = _dict(strategy_state)
    omar = _dict(omar_state)
    goal = _dict(wealth_goal)

    engine = _dict(capital.get("capital_engine"))
    current_capital = _first_number(
        capital, "current_capital_usd", "currentCapitalUsd", "available_usd", "availableUsd"
    ) or _first_number(
        engine, "current_capital_usd", "currentCapitalUsd", "available_usd", "availableUsd"
    )
    if current_capital <= 0:
        current_capital = _first_number(capital, "available_wei", "availableWei") / 1e18

    stable_cagr = _stable_cagr(outcomes, current_capital)
    drawdown = _drawdown(outcomes, current_capital)
    execution_realism = _execution_realism(outcomes)
    strategy_capacity = _first_number(
        strategy,
        "capacity_usd",
        "capacityUsd",
        "allocatable_usd",
        "allocatableUsd",
        "capacity_ratio",
        "capacityRatio",
    )
    treasury_reserves = _first_number(
        treasury, "reserves_usd", "reservesUsd", "available_usd", "availableUsd"
    )
    omar_confidence = _clamp(
        _first_number(
            omar,
            "confidence",
            "omar_confidence",
            "omarConfidence",
            "policy_confidence",
            "policyConfidence",
        )
    )
    prime_contract = _prime_contract(prime)

    blocks: list[str] = []
    if current_capital <= 0:
        blocks.append("capital_unavailable")
    if not outcomes:
        blocks.append("no_settled_outcome_evidence")
    if execution_realism < 0.5:
        blocks.append("execution_evidence_weak")
    if drawdown >= 0.20:
        blocks.append("drawdown_limit_pressure")
    if strategy_capacity <= 0:
        blocks.append("strategy_capacity_unavailable")
    if treasury_reserves <= 0:
        blocks.append("treasury_reserves_unavailable")
    if omar_confidence < 0.5:
        blocks.append("omar_confidence_low")

    requested_goal = _first_number(goal, "target_usd", "targetUsd", "goal_usd", "goalUsd")
    timeframe_days = max(0.0, _first_number(goal, "timeframe_days", "timeframeDays", "days"))
    aggressiveness = _clamp(
        _first_number(
            goal, "aggressiveness", "aggressiveness_multiplier", "aggressivenessMultiplier"
        ),
        0.0,
        2.0,
    )
    if aggressiveness == 0.0:
        aggressiveness = 1.0

    if requested_goal > current_capital:
        base_growth = max(0.0, stable_cagr)
        if timeframe_days > 0:
            base_growth = max(base_growth, 0.0) * timeframe_days / 365.25
        goal_multiplier = 1.0 + min(2.0, base_growth * aggressiveness)
        recommended_goal = current_capital * goal_multiplier
    else:
        recommended_goal = current_capital
    if requested_goal > 0:
        recommended_goal = min(recommended_goal, max(current_capital, requested_goal))

    readiness = (
        execution_realism * 0.35
        + _clamp(strategy_capacity / max(current_capital, 1e-9)) * 0.2
        + omar_confidence * 0.2
        + _clamp(treasury_reserves / max(current_capital, 1e-9)) * 0.15
        + _clamp(1.0 - drawdown / 0.2) * 0.1
    )
    if blocks or readiness < 0.55:
        risk_posture = "defensive"
    elif readiness < 0.75:
        risk_posture = "balanced"
    else:
        risk_posture = "growth"

    if risk_posture == "defensive":
        recommended_goal = min(recommended_goal, current_capital * 1.05)
    elif risk_posture == "balanced":
        recommended_goal = min(recommended_goal, current_capital * 1.15)

    next_goal = max(current_capital, recommended_goal)
    return GoalEvidenceSnapshot(
        current_capital=current_capital,
        stable_cagr=stable_cagr,
        drawdown=drawdown,
        execution_realism=execution_realism,
        strategy_capacity=max(0.0, strategy_capacity),
        prime_utilization_capacity=prime_contract,
        treasury_reserves=max(0.0, treasury_reserves),
        omar_confidence=omar_confidence,
        recommended_goal=max(current_capital, recommended_goal),
        next_goal=next_goal,
        risk_posture=risk_posture,
        block_reasons=tuple(dict.fromkeys(blocks)),
    )
