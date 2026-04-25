from __future__ import annotations

from typing import Any, Dict


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_dynamic_family_weights(
    *,
    base_targets: Dict[str, float],
    scorecards: Dict[str, Any],
    regime: str,
    capital_metrics: Dict[str, Any],
    covariance_penalties: Dict[str, float] | None = None,
) -> Dict[str, float]:
    families = list(base_targets.keys())
    cards = {str(x.get("family") or ""): x for x in list((scorecards or {}).get("families") or [])}
    cov = dict(covariance_penalties or {})
    utilization = float((capital_metrics or {}).get("utilization_rate") or 0.5)
    out: Dict[str, float] = {}
    for fam in families:
        base = float(base_targets.get(fam, 0.0) or 0.0)
        card = dict(cards.get(fam) or {})
        stability = float(card.get("stability") or 0.55)
        gas_eff = float(card.get("gasEfficiency") or 0.8)
        success = float(card.get("executionSuccessRate") or stability)
        dd_pen = min(
            0.8,
            float(card.get("drawdownPenaltyUsd") or 0.0)
            / max(1.0, abs(float(card.get("realizedPnlUsd") or 1.0))),
        )
        regime_perf = dict(card.get("regimePerformance") or {})
        rf = 1.0
        if regime_perf and regime in regime_perf:
            rp = dict(regime_perf.get(regime) or {})
            rf = _clip(
                0.75
                + 0.25 * float(rp.get("successRate", success) or success)
                + 0.10 * max(-1.0, min(1.0, float(rp.get("pnlUsd", 0.0) or 0.0))),
                0.6,
                1.35,
            )
        performance_factor = _clip(0.70 + 0.20 * success + 0.10 * stability, 0.55, 1.35)
        efficiency_factor = _clip(0.75 + 0.20 * min(2.0, gas_eff) + 0.05 * utilization, 0.60, 1.40)
        risk_penalty = _clip(1.0 - dd_pen - float(cov.get(fam, 0.0) or 0.0), 0.35, 1.0)
        out[fam] = base * rf * performance_factor * efficiency_factor * risk_penalty
    total = sum(out.values())
    if total <= 0:
        return {k: float(v) for k, v in base_targets.items()}
    return {k: round(v / total, 6) for k, v in out.items()}
