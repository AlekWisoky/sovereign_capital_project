from __future__ import annotations

from typing import Any, Dict, Mapping


def _int_like(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rate_pct(value: Any) -> float:
    """Normalize legacy fraction (0..1) or percentage (0..100) inputs."""
    try:
        raw = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if 0.0 <= raw <= 1.0:
        raw *= 100.0
    return max(0.0, min(100.0, raw))


def resolve_profit_promotion(
    *,
    capital_engine: Mapping[str, Any] | None,
    realized_profit_wei: int,
    reinvestment_policy: Mapping[str, Any] | None,
    previous_promoted_profit_wei: int = 0,
) -> Dict[str, Any]:
    """Resolve the canonical Treasury->deployable profit promotion.

    This is deliberately a pure authority kernel: it never mutates bankroll,
    Treasury, or execution state. The caller must persist/apply the returned
    promotion through the canonical capital-write boundary.

    ``capital_engine`` is the authority input. Promotion is incremental so the
    same cumulative realized profit cannot be promoted more than once.
    """
    engine = dict(capital_engine or {})
    policy = dict(reinvestment_policy or {})

    realized = max(0, _int_like(realized_profit_wei))
    previous = max(0, _int_like(previous_promoted_profit_wei))

    enabled = bool(engine.get("profit_promotion_enabled", engine.get("compounding_enabled", False)))
    rate_pct = _rate_pct(engine.get("profit_promotion_rate_pct", policy.get("reinvest_pct", 0.0)))
    eligible = int(realized * (rate_pct / 100.0)) if enabled else 0
    promoted_delta = max(0, eligible - previous)
    promoted_total = previous + promoted_delta

    deployable_before = max(0, _int_like(engine.get("deployable_bankroll_wei")))
    deployable_after = deployable_before + promoted_delta
    blocked_reason = ""
    if not enabled:
        blocked_reason = "profit_promotion_disabled"
    elif realized <= 0:
        blocked_reason = "no_realized_profit"
    elif rate_pct <= 0.0:
        blocked_reason = "profit_promotion_rate_zero"
    elif promoted_delta <= 0:
        blocked_reason = "profit_already_promoted"

    return {
        "enabled": enabled,
        "rate_pct": round(rate_pct, 8),
        "realized_profit_wei": realized,
        "eligible_profit_wei": eligible,
        "previous_promoted_profit_wei": previous,
        "promoted_profit_delta_wei": promoted_delta,
        "promoted_profit_wei": promoted_total,
        "deployable_bankroll_before_wei": deployable_before,
        "deployable_bankroll_after_wei": deployable_after,
        "promotion_applied": promoted_delta > 0,
        "reason_code": "profit_promoted" if promoted_delta > 0 else blocked_reason,
        "authority": "capital_engine_state",
        "write_boundary": "canonical_capital_write_v1",
    }
