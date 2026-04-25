from __future__ import annotations

from typing import Any, Dict, List

from .models import OpportunityEnvelope, SafeSizePoint


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_LEGS_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_TOKEN_PATH_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except _SAFE_FLOAT_EXCEPTIONS:
        return default


def _legs(opp: Any) -> list[Any]:
    try:
        legs = getattr(getattr(opp, "route", None), "legs", []) or []
        return list(legs)
    except _SAFE_LEGS_EXCEPTIONS:
        return []


def _route_family(opp: Any) -> str:
    legs = _legs(opp)
    strat = str(getattr(opp, "strategy", "") or "unknown")
    if not legs:
        return strat
    try:
        venues = ">".join(str(getattr(x, "venue", "") or "") for x in legs)
        tokens = ">".join(str(getattr(x, "token_in", "") or "") for x in legs[:1] + legs[-1:])
        return f"{strat}|{venues}|{tokens}"
    except _SAFE_LEGS_EXCEPTIONS:
        return strat


def _strategy_family(opp: Any, meta: Dict[str, Any]) -> str:
    family = ""
    if isinstance(meta, dict):
        family = str(meta.get("strategy_family") or "")
    if family:
        return family
    return str(getattr(opp, "strategy", "") or "flashloan_atomic")


def build_opportunity_envelope(
    opp: Any, *, chain_id: int, regime: str = "unknown"
) -> OpportunityEnvelope:
    meta = (
        dict(getattr(opp, "meta", {}) or {}) if isinstance(getattr(opp, "meta", None), dict) else {}
    )
    strategy_family = _strategy_family(opp, meta)
    unit = dict(meta.get("unit_econ") or {}) if isinstance(meta.get("unit_econ"), dict) else {}
    legs = _legs(opp)
    venues: List[str] = [str(getattr(x, "venue", "") or "") for x in legs]
    token_path: List[str] = []
    try:
        for idx, leg in enumerate(legs):
            if idx == 0:
                token_path.append(str(getattr(leg, "token_in", "") or ""))
            token_path.append(str(getattr(leg, "token_out", "") or ""))
    except _SAFE_TOKEN_PATH_EXCEPTIONS:
        token_path = []
    expected_profit_usd = _safe_float(
        getattr(opp, "expected_profit_usd", 0.0) or unit.get("expected_profit_usd_micro", 0.0), 0.0
    )
    if expected_profit_usd > 1000.0:
        expected_profit_usd = expected_profit_usd / 1_000_000.0
    gas_estimate_usd = _safe_float(unit.get("gas_cost_usd_micro", 0.0), 0.0)
    if gas_estimate_usd > 1000.0:
        gas_estimate_usd = gas_estimate_usd / 1_000_000.0
    mr = _safe_float(meta.get("margin_ratio"), 0.02)
    gas_ratio = _safe_float(
        meta.get("gas_ratio"), min(1.0, gas_estimate_usd / max(expected_profit_usd, 1e-9))
    )
    p_success = _safe_float(meta.get("p_success"), 0.70)
    mev = _safe_float(
        (((meta.get("aqe") or {}) if isinstance(meta.get("aqe"), dict) else {}).get("mev_risk")),
        0.0,
    )
    default_fragility = (
        0.28 + (gas_ratio * 0.20) + (max(mev, 0.0) * 0.18) + max(0.0, 0.20 - mr) * 0.55
    )
    liquidity_fragility = max(
        0.05, min(0.98, _safe_float(meta.get("liquidity_fragility"), default_fragility))
    )
    default_slippage = 0.12 + (gas_ratio * 0.28) + (liquidity_fragility * 0.22)
    slippage_sensitivity = max(
        0.05, min(0.95, _safe_float(meta.get("slippage_sensitivity"), default_slippage))
    )
    freshness_score = max(
        0.05,
        min(
            1.0,
            _safe_float(
                meta.get("freshness_score"), p_success * (1.0 - min(0.45, gas_ratio * 0.35))
            ),
        ),
    )
    venue_reliability_score = max(
        0.1, min(1.0, _safe_float(meta.get("venue_reliability_score"), 0.75))
    )
    latency_half_life_ms = int(
        max(150, _safe_float(meta.get("latency_half_life_ms"), 500 + (1800.0 * mr)))
    )
    private_send_preference = bool(
        meta.get("private_send_preference", mev >= 0.65 or gas_ratio >= 0.55)
    )
    failure_cost_estimate = max(
        0.0, gas_estimate_usd + (expected_profit_usd * (0.06 + (0.08 * liquidity_fragility)))
    )
    safe_curve: List[SafeSizePoint] = []
    base_expected = max(0.0, expected_profit_usd)
    for mult in (0.35, 0.50, 0.75, 1.00, 1.25):
        scaled_profit = base_expected * mult
        safe_curve.append(
            SafeSizePoint(
                size_mult=float(mult),
                expected_profit_usd=float(scaled_profit),
                slippage_cost_usd=float(
                    scaled_profit * slippage_sensitivity * max(0.03, mult - 0.10) * 0.14
                ),
                interference_penalty_usd=float(
                    scaled_profit * max(mev, 0.0) * max(0.0, mult - 0.20) * 0.14
                ),
                latency_decay_cost_usd=float(
                    scaled_profit * max(0.0, 1.0 - freshness_score) * 0.08
                ),
            )
        )
    return OpportunityEnvelope(
        opportunity_id=str(getattr(opp, "id", "") or ""),
        route_id=str(getattr(opp, "route_id", "") or ""),
        route_family=_route_family(opp),
        expected_profit_usd=float(expected_profit_usd),
        gas_estimate_usd=float(gas_estimate_usd),
        slippage_sensitivity=float(slippage_sensitivity),
        liquidity_fragility=float(liquidity_fragility),
        latency_half_life_ms=int(latency_half_life_ms),
        mempool_copy_risk=float(
            max(0.0, min(1.0, mev if mev > 0.0 else gas_ratio * 0.55 + liquidity_fragility * 0.35))
        ),
        venue_reliability_score=float(venue_reliability_score),
        simulation_confidence=float(max(0.0, min(1.0, p_success))),
        safe_size_curve=safe_curve,
        failure_cost_estimate=float(failure_cost_estimate),
        freshness_score=float(freshness_score),
        private_send_preference=bool(private_send_preference),
        chain_id=int(chain_id),
        token_path=token_path,
        venues=venues,
        metadata={
            "regime": str(regime),
            "meta": meta,
            "strategy_family": strategy_family,
        },
    )
