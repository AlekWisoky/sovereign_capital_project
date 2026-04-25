from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from .runtime_services.profitability_truth import inspect_profit_after_costs_truth


_SAFE_INT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_META_EXCEPTIONS = (AttributeError, TypeError)
_SAFE_LEG_EXCEPTIONS = (AttributeError, TypeError)
_SAFE_AMOUNT_IN_EXCEPTIONS = (AttributeError, TypeError, IndexError)


def _int(x: Any) -> int:
    try:
        return int(str(x))
    except _SAFE_INT_EXCEPTIONS:
        return 0


def _safe_div(num: float, den: float) -> float:
    if den == 0.0:
        return 0.0
    return float(num) / float(den)


@dataclass(frozen=True)
class FeatureVector:
    """Lightweight feature vector for decisioning and RL.

    Design goals:
    - Cheap to compute per opportunity (no extra RPC).
    - Uses bigint-ish values from state/safety meta, but emits floats/ints.
    - Stable across versions (additive only).
    """

    amount_in_wei: int
    profit_after_costs_wei: int
    gas_cost_wei: int
    flash_fee_wei: int
    legs: int
    has_univ3: int
    has_curve: int
    has_balancer: int
    profit_ratio: float
    gas_ratio: float
    margin_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount_in_wei": self.amount_in_wei,
            "profit_after_costs_wei": self.profit_after_costs_wei,
            "gas_cost_wei": self.gas_cost_wei,
            "flash_fee_wei": self.flash_fee_wei,
            "legs": self.legs,
            "has_univ3": self.has_univ3,
            "has_curve": self.has_curve,
            "has_balancer": self.has_balancer,
            "profit_ratio": self.profit_ratio,
            "gas_ratio": self.gas_ratio,
            "margin_ratio": self.margin_ratio,
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_features(opp: Any) -> FeatureVector:
    """Build features for a given Opportunity.

    Relies on runtime to have already annotated `opp.meta["safety"]`.
    If missing, we fall back conservatively.
    """
    try:
        amount_in_raw = (
            getattr(getattr(opp, "route", None), "legs", [{}])[0].amount_in
            if getattr(opp, "route", None) and getattr(opp.route, "legs", None)
            else 0
        )
    except _SAFE_AMOUNT_IN_EXCEPTIONS:
        amount_in_raw = 0
    amount_in = _int(amount_in_raw)
    legs = len(getattr(getattr(opp, "route", None), "legs", []) or [])
    safety = {}
    try:
        safety = _mapping(_mapping(getattr(opp, "meta", None)).get("safety"))
    except _SAFE_META_EXCEPTIONS:
        safety = {}

    profit_truth = inspect_profit_after_costs_truth(getattr(opp, "meta", None))
    profit_after = int(profit_truth.value_wei) if bool(profit_truth.verified) else 0
    gas_cost = _int(safety.get("gas_cost_wei"))
    flash_fee = _int(safety.get("flashloan_fee_wei"))

    has_univ3 = 0
    has_curve = 0
    has_balancer = 0
    try:
        for leg in getattr(getattr(opp, "route", None), "legs", []) or []:
            if getattr(leg, "dex", "") == "univ3":
                has_univ3 = 1
            elif getattr(leg, "dex", "") == "curve":
                has_curve = 1
            elif getattr(leg, "dex", "") == "balancer":
                has_balancer = 1
    except _SAFE_LEG_EXCEPTIONS:
        pass

    profit_ratio = _safe_div(float(profit_after), float(amount_in))
    gas_ratio = _safe_div(float(gas_cost), float(amount_in))
    margin_ratio = profit_ratio - gas_ratio

    return FeatureVector(
        amount_in_wei=amount_in,
        profit_after_costs_wei=profit_after,
        gas_cost_wei=gas_cost,
        flash_fee_wei=flash_fee,
        legs=legs,
        has_univ3=has_univ3,
        has_curve=has_curve,
        has_balancer=has_balancer,
        profit_ratio=profit_ratio,
        gas_ratio=gas_ratio,
        margin_ratio=margin_ratio,
    )
