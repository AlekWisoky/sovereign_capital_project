from __future__ import annotations

from math import sqrt
from typing import Any, Dict, List


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _quantile(sorted_values: List[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = int(max(0, min(len(sorted_values) - 1, round((len(sorted_values) - 1) * q))))
    return float(sorted_values[idx])


def _mean(values: List[float]) -> float:
    return sum(values) / float(max(1, len(values)))


def _cov(x: List[float], y: List[float]) -> float:
    n = min(len(x), len(y))
    if n <= 1:
        return 0.0
    xs = x[-n:]
    ys = y[-n:]
    mx = _mean(xs)
    my = _mean(ys)
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / float(n - 1)


def _family_histories(
    scorecards: Dict[str, Any], drawdown_state: Dict[str, Any]
) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {
        str(k): [float(vv or 0.0) for vv in list(v or [])[-60:]]
        for k, v in dict((drawdown_state or {}).get("familyReturnHistory") or {}).items()
    }
    for item in list((scorecards or {}).get("families") or []):
        if not isinstance(item, dict):
            continue
        family = str(item.get("family") or "")
        if family in out and out[family]:
            continue
        regimes = dict(item.get("regimePerformance") or {})
        series: List[float] = []
        for _, row in sorted(regimes.items()):
            if isinstance(row, dict):
                count = int(row.get("count") or 0)
                pnl = float(row.get("pnlUsd") or 0.0)
                if count > 0:
                    per = pnl / float(count)
                    series.extend([per] * min(count, 12))
        if series:
            out[family] = series[-60:]
    return out


def compute_portfolio_risk(
    *,
    capital_state: Dict[str, Any],
    covariance_penalties: Dict[str, float],
    engine_state: Dict[str, Any],
    scorecards: Dict[str, Any] | None = None,
    drawdown_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    cap = dict((capital_state or {}).get("capital_engine") or {})
    util = float(
        ((capital_state or {}).get("capital_efficiency_metrics") or {}).get("utilizationRate")
        or 0.0
    )
    drawdown = float(
        (drawdown_state or {}).get("drawdownPct")
        or cap.get("drawdown_pct")
        or cap.get("drawdownPct")
        or 0.0
    )
    family_targets = dict(cap.get("family_targets") or {})
    max_family = max([float(v or 0.0) for v in family_targets.values()] + [0.0])
    cov_penalty = max([float(v or 0.0) for v in covariance_penalties.values()] + [0.0])
    engs = list((engine_state or {}).get("summary", {}).get("engines") or [])
    active = sum(
        1 for x in engs if str((x or {}).get("status") or "") not in {"disabled", "observe_only"}
    )

    histories = _family_histories(scorecards or {}, drawdown_state or {})
    weighted_returns: List[float] = []
    fam_keys = sorted(histories.keys())
    max_len = max([len(v) for v in histories.values()] + [0])
    for idx in range(max_len):
        total = 0.0
        for family in fam_keys:
            series = histories.get(family) or []
            if idx < len(series):
                weight = float(family_targets.get(family, 0.0) or 0.0)
                total += float(series[idx]) * max(0.0, weight)
        weighted_returns.append(total)
    if not weighted_returns:
        weighted_returns = [0.0]
    sorted_returns = sorted(weighted_returns)
    var95 = abs(min(0.0, _quantile(sorted_returns, 0.05)))
    var99 = abs(min(0.0, _quantile(sorted_returns, 0.01)))
    es95_tail = [x for x in sorted_returns if x <= _quantile(sorted_returns, 0.05)] or [0.0]
    es99_tail = [x for x in sorted_returns if x <= _quantile(sorted_returns, 0.01)] or [0.0]
    es95 = abs(min(0.0, _mean(es95_tail)))
    es99 = abs(min(0.0, _mean(es99_tail)))

    regimes = dict((drawdown_state or {}).get("regimeReturnHistory") or {})
    regime_covariance: Dict[str, Dict[str, float]] = {}
    for fam_a in fam_keys:
        row: Dict[str, float] = {}
        for fam_b in fam_keys:
            row[fam_b] = round(
                _cov(histories.get(fam_a) or [0.0], histories.get(fam_b) or [0.0]), 6
            )
        regime_covariance[fam_a] = row

    exposure_limits = {
        family: round(
            min(
                0.45,
                max(
                    0.05,
                    0.20
                    + max(
                        0.0,
                        0.15
                        - float(
                            (drawdown_state or {}).get("familyDrawdown", {}).get(family, 0.0) or 0.0
                        )
                        / 100.0,
                    ),
                ),
            ),
            6,
        )
        for family in sorted(family_targets.keys())
    }
    exposure_breaches = {
        family: {
            "target": round(float(target or 0.0), 6),
            "limit": float(exposure_limits.get(family) or 0.0),
        }
        for family, target in sorted(family_targets.items())
        if float(target or 0.0) > float(exposure_limits.get(family) or 0.0)
    }

    stress = {
        "gas_spike": round(var95 + util * 0.12 + 0.05, 6),
        "bridge_delay": round(var95 + 0.03, 6),
        "oracle_drift": round(var99 + cov_penalty * 0.30 + 0.05, 6),
        "pool_imbalance": round(var95 + max_family * 0.15 + 0.04, 6),
        "relay_censorship": round(var95 + 0.02 + util * 0.05, 6),
        "stablecoin_depeg": round(var99 + max_family * 0.20 + 0.08, 6),
    }

    risk_score = min(
        1.0,
        max(
            0.0,
            0.18 * drawdown
            + 0.17 * max_family
            + 0.12 * cov_penalty
            + 0.10 * util
            + 0.18 * var95
            + 0.15 * es95
            + 0.10 * max(stress.values() or [0.0]),
        ),
    )
    posture = "normal"
    if risk_score >= 0.85:
        posture = "severe"
    elif risk_score >= 0.65:
        posture = "elevated"

    return {
        "riskScore": round(risk_score, 6),
        "posture": posture,
        "components": {
            "drawdown": round(drawdown, 6),
            "familyConcentration": round(max_family, 6),
            "covariancePenalty": round(cov_penalty, 6),
            "utilization": round(util, 6),
            "var95": round(var95, 6),
            "var99": round(var99, 6),
            "expectedShortfall95": round(es95, 6),
            "expectedShortfall99": round(es99, 6),
        },
        "historicalSimulation": {
            "returns": [round(x, 6) for x in weighted_returns[-60:]],
            "var95": round(var95, 6),
            "var99": round(var99, 6),
            "expectedShortfall95": round(es95, 6),
            "expectedShortfall99": round(es99, 6),
        },
        "regimeCovariance": regime_covariance,
        "exposureLimits": exposure_limits,
        "exposureBreaches": exposure_breaches,
        "stressScenarios": stress,
        "activeEngines": active,
    }
