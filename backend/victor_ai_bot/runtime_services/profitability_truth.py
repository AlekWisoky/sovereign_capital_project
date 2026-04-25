from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Mapping

from ..profitability_state import profitability_state_view


@dataclass(frozen=True)
class ProfitAfterCostsTruth:
    value_wei: int
    verified: bool
    positive: bool
    reason_code: str
    meta_present: bool
    safety_present: bool
    meta_value_wei: int | None = None
    safety_value_wei: int | None = None
    contract_present: bool = False
    stale: bool = False
    revalidated: bool = False


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _parse_profit_value(value: Any) -> int | None:
    try:
        return int(str(value or "0"))
    except (TypeError, ValueError):
        return None


def _meta_like_dict(meta_like: Any) -> Dict[str, Any]:
    if isinstance(meta_like, Mapping):
        if isinstance(meta_like.get("meta"), Mapping):
            return _safe_dict(meta_like.get("meta"))
        return _safe_dict(meta_like)
    return _safe_dict(getattr(meta_like, "meta", None))


def _legacy_truth(meta: Dict[str, Any]) -> ProfitAfterCostsTruth:
    safety = _safe_dict(meta.get("safety"))

    meta_present = "profit_after_costs" in meta
    safety_present = "profit_after_costs_wei" in safety

    if not meta_present and not safety_present:
        return ProfitAfterCostsTruth(
            value_wei=0,
            verified=False,
            positive=False,
            reason_code="profit_after_costs_unavailable",
            meta_present=False,
            safety_present=False,
        )

    meta_value = _parse_profit_value(meta.get("profit_after_costs")) if meta_present else None
    safety_value = (
        _parse_profit_value(safety.get("profit_after_costs_wei")) if safety_present else None
    )

    if (meta_present and meta_value is None) or (safety_present and safety_value is None):
        return ProfitAfterCostsTruth(
            value_wei=0,
            verified=False,
            positive=False,
            reason_code="profit_after_costs_invalid",
            meta_present=meta_present,
            safety_present=safety_present,
            meta_value_wei=meta_value,
            safety_value_wei=safety_value,
        )

    if meta_present and safety_present and meta_value != safety_value:
        return ProfitAfterCostsTruth(
            value_wei=0,
            verified=False,
            positive=False,
            reason_code="profit_after_costs_mismatch",
            meta_present=True,
            safety_present=True,
            meta_value_wei=meta_value,
            safety_value_wei=safety_value,
        )

    value_wei = meta_value if meta_present else safety_value
    value_wei = int(value_wei or 0)
    positive = value_wei > 0
    return ProfitAfterCostsTruth(
        value_wei=max(0, value_wei),
        verified=True,
        positive=positive,
        reason_code="ok" if positive else "profit_after_costs_not_positive",
        meta_present=meta_present,
        safety_present=safety_present,
        meta_value_wei=meta_value,
        safety_value_wei=safety_value,
    )


def _canonical_contract_present(meta: Dict[str, Any]) -> bool:
    safety = _safe_dict(meta.get("safety"))
    return bool(
        _safe_dict(meta.get("profitability"))
        or _safe_dict(meta.get("post_mutation_revalidation"))
        or _safe_dict(meta.get("profitability_continuity"))
        or bool(safety.get("revalidated", False))
    )


def _canonical_view(meta_like: Any, meta: Dict[str, Any]) -> Dict[str, Any]:
    carrier = meta_like
    if isinstance(meta_like, Mapping) and "meta" not in meta_like:
        carrier = SimpleNamespace(meta=meta)
    return _safe_dict(profitability_state_view(carrier))


def inspect_profit_after_costs_truth(meta_like: Any) -> ProfitAfterCostsTruth:
    """Return canonical after-fee profit truth.

    Legacy opportunities may only carry scan-time values in:
    - meta["profit_after_costs"]
    - meta["safety"]["profit_after_costs_wei"]

    Upgraded opportunities also carry canonical profitability contracts that can
    invalidate otherwise-positive scan-time values when the route mutates,
    profitability becomes stale, or revalidation fails. Once those contracts are
    present, they dominate legacy fallbacks to preserve fail-closed behavior.
    """

    meta = _meta_like_dict(meta_like)
    legacy = _legacy_truth(meta)
    if not _canonical_contract_present(meta):
        return legacy

    view = _canonical_view(meta_like, meta)
    verified = (
        bool(view.get("valid", False))
        and not bool(view.get("stale", True))
        and bool(view.get("revalidated", False) or view.get("authoritative", False))
    )
    after_costs_wei = int(view.get("profitAfterCostsWeiInt") or 0)
    positive = bool(verified and after_costs_wei > 0)
    reason_code = str(
        view.get("reason") or ("ok" if positive else "profitability_contract_not_positive")
    )
    return ProfitAfterCostsTruth(
        value_wei=max(0, after_costs_wei) if verified else 0,
        verified=verified,
        positive=positive,
        reason_code=reason_code,
        meta_present=legacy.meta_present,
        safety_present=legacy.safety_present,
        meta_value_wei=legacy.meta_value_wei,
        safety_value_wei=legacy.safety_value_wei,
        contract_present=True,
        stale=bool(view.get("stale", False)),
        revalidated=bool(view.get("revalidated", False) or view.get("authoritative", False)),
    )


def opportunity_profit_after_costs_info(opportunity_like: Any) -> tuple[int, bool, str]:
    """Return canonical after-fee profit info for an opportunity-like object."""

    truth = inspect_profit_after_costs_truth(opportunity_like)
    return truth.value_wei, truth.verified, truth.reason_code


def opportunity_profit_sort_key(opportunity_like: Any) -> tuple[int, int, str]:
    """Return a deterministic profitability ranking key.

    Ranking precedence:
    1. Verified positive after-fee truth.
    2. Unverified but positive scan-time estimates (after-gas first, then gross).
    3. Verified non-positive after-fee truth.
    4. Everything else.

    Once a canonical profitability contract exists, do not resurrect the
    opportunity with gross or scan-time fallbacks when that contract is stale,
    invalid, or non-positive.
    """

    truth = inspect_profit_after_costs_truth(opportunity_like)
    profit_after = int(truth.value_wei)
    route_id = str(
        getattr(opportunity_like, "route_id", "") or getattr(opportunity_like, "id", "") or ""
    )
    if truth.verified and profit_after > 0:
        return (3, int(profit_after), route_id)

    if truth.contract_present:
        return (1 if truth.verified else 0, int(profit_after), route_id)

    meta = _safe_dict(
        getattr(opportunity_like, "meta", None) if opportunity_like is not None else None
    )
    fallback_after_gas = (
        _parse_profit_value(meta.get("profit_after_gas_estimate_wei"))
        if "profit_after_gas_estimate_wei" in meta
        else None
    )
    fallback_gross = _parse_profit_value(getattr(opportunity_like, "expected_profit_raw", 0))
    fallback_value = fallback_after_gas if fallback_after_gas is not None else fallback_gross
    fallback_value = int(fallback_value or 0)
    if fallback_value > 0:
        return (2, fallback_value, route_id)
    if truth.verified:
        return (1, int(profit_after), route_id)
    return (0, fallback_value, route_id)
