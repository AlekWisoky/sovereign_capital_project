from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Dict, List, Tuple

from victor_ai_bot.fund_os.family_identity import (
    family_alias_candidates as identity_alias_candidates,
)
from victor_ai_bot.fund_os.family_identity import family_identity

FAMILY_CAPITAL_PLAN_VERSION = "family_capital_plan_v1"


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _unique(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        text = str(value or "")
        if text and text not in out:
            out.append(text)
    return out


def canonical_family_id(family: str) -> str:
    info = family_identity(family)
    return str(info.get("capitalFamily") or str(family or ""))


def family_alias_candidates(families: str | Iterable[str]) -> List[str]:
    return _unique(identity_alias_candidates(families))


def resolve_family_target(
    *, family_targets: Mapping[str, Any] | None, family: str | Iterable[str]
) -> tuple[str, float, bool]:
    targets = dict(family_targets or {})
    for candidate in family_alias_candidates(family):
        if candidate in targets:
            return candidate, _safe_float(targets.get(candidate)), True
    return "", 0.0, False


def resolve_family_allocation(
    *, family_allocations_wei: Mapping[str, Any] | None, family: str | Iterable[str]
) -> tuple[str, int, bool]:
    allocations = dict(family_allocations_wei or {})
    for candidate in family_alias_candidates(family):
        if candidate in allocations:
            return candidate, max(0, _safe_int(allocations.get(candidate))), True
    return "", 0, False


def resolve_family_capital_limit(
    *, capital_engine: Mapping[str, Any] | None, family: str | Iterable[str]
) -> dict[str, Any]:
    engine = dict(capital_engine or {})
    target_key, target, target_known = resolve_family_target(
        family_targets=engine.get("family_targets"),
        family=family,
    )
    allocation_key, allocation_wei, allocation_known = resolve_family_allocation(
        family_allocations_wei=engine.get("family_allocations_wei"),
        family=family,
    )
    requested_family = (
        str(family) if isinstance(family, str) else str(next(iter(list(family or [])), ""))
    )
    canonical = canonical_family_id(requested_family)
    return {
        "requested_family": requested_family,
        "canonical_family": canonical,
        "target_known": bool(target_known),
        "resolved_target_key": target_key,
        "family_target": float(round(max(0.0, target), 8)),
        "allocation_known": bool(allocation_known),
        "resolved_allocation_key": allocation_key,
        "family_allocation_wei": int(max(0, allocation_wei)),
        "aliases": [
            alias
            for alias in family_alias_candidates(requested_family)
            if alias != requested_family
        ],
    }


def build_family_capital_plan(
    *,
    capital_engine: Mapping[str, Any] | None,
    family_metrics: Mapping[str, Any] | None = None,
    deployable_usd: float = 0.0,
) -> List[Dict[str, Any]]:
    engine = dict(capital_engine or {})
    targets = {
        str(k): max(0.0, _safe_float(v))
        for k, v in dict(engine.get("family_targets") or {}).items()
    }
    allocations = {
        str(k): max(0, _safe_int(v))
        for k, v in dict(engine.get("family_allocations_wei") or {}).items()
    }
    metrics_by_family = {
        str(k): dict(v or {})
        for k, v in dict(family_metrics or {}).items()
        if isinstance(v, Mapping)
    }
    raw_families = _unique([*targets.keys(), *allocations.keys(), *metrics_by_family.keys()])
    grouped: dict[str, list[str]] = {}
    for family in raw_families:
        canonical = canonical_family_id(family)
        grouped.setdefault(canonical or family, []).append(family)

    plan: List[Dict[str, Any]] = []
    for canonical, raw_keys in grouped.items():
        candidates = family_alias_candidates([canonical, *raw_keys])
        target_key = next((candidate for candidate in candidates if candidate in targets), "")
        allocation_key = next(
            (candidate for candidate in candidates if candidate in allocations), ""
        )
        metric_key = next(
            (candidate for candidate in candidates if candidate in metrics_by_family), ""
        )
        display_id = target_key or allocation_key or metric_key or canonical
        target = max(0.0, _safe_float(targets.get(target_key))) if target_key else 0.0
        allocation_wei = max(0, _safe_int(allocations.get(allocation_key))) if allocation_key else 0
        target_implied_capital_usd = round(max(0.0, float(deployable_usd)) * target, 6)
        allocation_usd = round(allocation_wei / 1e18, 6) if allocation_key else 0.0
        capital_usd = allocation_usd if allocation_key else target_implied_capital_usd
        if target_key and allocation_key:
            drift = abs(allocation_usd - target_implied_capital_usd)
            tolerance = max(0.01, abs(float(deployable_usd)) * 0.05)
            synchronization_status = "aligned" if drift <= tolerance else "drifted"
        elif target_key:
            synchronization_status = "target_only"
        elif allocation_key:
            synchronization_status = "allocation_only"
        else:
            synchronization_status = "unplanned"
        if target > 0.0 or allocation_wei > 0:
            status = "active"
        elif target_key:
            status = "paused"
        else:
            status = "unplanned"
        metrics = dict(metrics_by_family.get(metric_key or display_id) or {})
        aliases = _unique(
            [*raw_keys, *[candidate for candidate in candidates if candidate != display_id]]
        )
        aliases = [alias for alias in aliases if alias != display_id]
        plan.append(
            {
                "id": display_id,
                "canonicalId": canonical,
                "name": display_id.replace("_", " ").title(),
                "capitalUsd": float(round(capital_usd, 6)),
                "allocatedUsd": float(round(allocation_usd, 6)),
                "targetImpliedCapitalUsd": float(round(target_implied_capital_usd, 6)),
                "targetPct": float(round(target * 100.0, 4)),
                "targetKnown": bool(target_key),
                "allocationKnown": bool(allocation_key),
                "resolvedTargetKey": target_key,
                "resolvedAllocationKey": allocation_key,
                "synchronizationStatus": synchronization_status,
                "status": status,
                "aliases": aliases,
                "roiPct": _safe_float(metrics.get("gasEfficiency")),
                "volPct": _safe_float(metrics.get("competitionPressure")),
                "riskScore": int(
                    max(
                        0.0,
                        min(
                            100.0,
                            _safe_float(
                                metrics.get("stability"),
                            )
                            * 100.0,
                        ),
                    )
                ),
            }
        )
    plan.sort(
        key=lambda item: (
            float(item.get("targetPct") or 0.0),
            float(item.get("capitalUsd") or 0.0),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return plan
