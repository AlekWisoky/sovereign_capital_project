from __future__ import annotations

from typing import Any, Dict, Iterable

from .capital_buckets import CapitalBuckets, default_buckets
from .family_allocator import compute_dynamic_family_weights
from .risk_controls import drawdown_contraction


# Capital targets use canonical treasury/runtime family identifiers.  Aliases are
# deliberately explicit so V1 cannot accidentally allocate to an unavailable family.
_CAPITAL_FAMILY_ALIASES = {
    "flash_arb": "flashloan_atomic",
    "flashloan_atomic": "flashloan_atomic",
    "funding_arb": "funding_arb",
    "cex_dex_arb": "cross_cex_dex",
    "cross_cex_dex": "cross_cex_dex",
    "liquidation_capture": "liquidation_anticipation",
    "liquidation_anticipation": "liquidation_anticipation",
    "mev_search": "mev_search",
    "volatility_market_making": "volatility_event_overlay",
}


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def family_targets(
    *, regime: str, aggressiveness_level: str, eligible_families: Iterable[str] | None = None
) -> Dict[str, float]:
    base = {
        "flashloan_atomic": 0.46,
        "liquidation_anticipation": 0.10,
        "oracle_drift": 0.08,
        "liquidity_migration": 0.08,
        "volatility_event_overlay": 0.08,
        "cross_cex_dex": 0.07,
        "funding_arb": 0.08,
        "cross_chain_arb": 0.02,
        "mev_search": 0.02,
        "auto_generated_strategy": 0.01,
    }
    reg = str(regime or "balanced")
    if reg == "high_volatility":
        base["volatility_event_overlay"] += 0.06
        base["flashloan_atomic"] -= 0.04
        base["mev_search"] += 0.02
    elif reg == "gas_spike":
        base["flashloan_atomic"] += 0.06
        base["liquidity_migration"] -= 0.03
        base["volatility_event_overlay"] -= 0.03
    elif reg == "low_volatility":
        base["liquidity_migration"] += 0.05
        base["oracle_drift"] += 0.03
        base["volatility_event_overlay"] -= 0.04
        base["flashloan_atomic"] -= 0.04
        base["mev_search"] += 0.02
    elif reg == "bear":
        base["liquidation_anticipation"] += 0.05
        base["oracle_drift"] += 0.04
        base["flashloan_atomic"] -= 0.05
        base["funding_arb"] += 0.03

    if eligible_families is not None:
        eligible = {
            _CAPITAL_FAMILY_ALIASES.get(str(family), str(family))
            for family in eligible_families
            if str(family)
        }
        # An empty/unknown eligibility set is fail-closed rather than a reason to
        # re-enable the historical multi-family target table.
        if not eligible:
            eligible = {"flashloan_atomic"}
        base = {key: value for key, value in base.items() if key in eligible}
        if not base:
            base = {"flashloan_atomic": 1.0}

    total = sum(base.values())
    return {k: round(v / max(1e-9, total), 6) for k, v in base.items()}


def allocate_capital(
    *,
    estimated_capital_wei: int,
    drawdown_pct: float,
    regime: str,
    aggressiveness_level: str,
    scorecards: Dict[str, Any] | None = None,
    capital_metrics: Dict[str, Any] | None = None,
    covariance_penalties: Dict[str, float] | None = None,
    eligible_families: Iterable[str] | None = None,
) -> Dict[str, Any]:
    buckets = default_buckets(drawdown_pct=drawdown_pct, aggressiveness_level=aggressiveness_level)
    cap = max(1, int(estimated_capital_wei))
    contraction = drawdown_contraction(drawdown_pct=float(drawdown_pct))
    deployable = int(
        cap * buckets.execution_capital_pct * float(contraction.get("contraction_factor") or 1.0)
    )
    reserve = int(cap * buckets.reserve_capital_pct)
    experimental = int(
        cap
        * buckets.experimental_capital_pct
        * float(contraction.get("experimental_cap_factor") or 1.0)
    )
    buffer = int(cap * buckets.drawdown_buffer_pct)
    treasury = int(cap * buckets.treasury_offramp_pct)
    fam_targets = family_targets(
        regime=regime,
        aggressiveness_level=aggressiveness_level,
        eligible_families=eligible_families,
    )
    if scorecards is not None or capital_metrics is not None or covariance_penalties is not None:
        fam_targets = compute_dynamic_family_weights(
            base_targets=fam_targets,
            scorecards=scorecards or {"families": []},
            regime=str(regime),
            capital_metrics=capital_metrics or {},
            covariance_penalties=covariance_penalties or {},
        )
        # Dynamic weighting is allowed to re-rank eligible families, never to add
        # an ineligible historical family back into the capital plan.
        if eligible_families is not None:
            eligible = {
                _CAPITAL_FAMILY_ALIASES.get(str(family), str(family))
                for family in eligible_families
                if str(family)
            }
            if not eligible:
                eligible = {"flashloan_atomic"}
            fam_targets = {
                key: value for key, value in fam_targets.items() if key in eligible
            } or {"flashloan_atomic": 1.0}
            total = sum(max(0.0, float(value)) for value in fam_targets.values())
            fam_targets = {
                key: round(max(0.0, float(value)) / max(1e-9, total), 6)
                for key, value in fam_targets.items()
            }
    fam_alloc = {k: int(deployable * float(v)) for k, v in fam_targets.items()}
    return {
        "deployable_bankroll_wei": deployable,
        "reserve_bankroll_wei": reserve,
        "experimental_bankroll_wei": experimental,
        "drawdown_buffer_wei": buffer,
        "treasury_offramp_wei": treasury,
        "capital_buckets": buckets.to_dict(),
        "family_targets": fam_targets,
        "family_allocations_wei": fam_alloc,
        "drawdown_adjustment": round(_clip(1.0 - (drawdown_pct / 100.0), 0.20, 1.0), 6),
        "drawdown_contraction": contraction,
    }
