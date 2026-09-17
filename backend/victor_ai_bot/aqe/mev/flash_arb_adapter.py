from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable, List

from ...calldata_builder import build_execute_calldata
from ...flashloan_providers import is_executable_flashloan_provider, normalize_flashloan_provider
from ...models import Opportunity, Route, RouteLeg
from ...route_encoding import EncLeg, route_id_hex
from .simulator import validate_deterministic_simulation_evidence


_ALLOWED_DEXES = {"univ3", "curve", "balancer"}


def _address(value: Any) -> str:
    text = str(value or "")
    if len(text) != 42 or not text.startswith("0x"):
        return ""
    try:
        int(text[2:], 16)
    except ValueError:
        return ""
    return text


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _validated_leg(raw: Any) -> RouteLeg | None:
    if not isinstance(raw, Mapping):
        return None
    dex = str(raw.get("dex") or "")
    if dex not in _ALLOWED_DEXES:
        return None
    venue = _address(raw.get("venue"))
    token_in = _address(raw.get("token_in"))
    token_out = _address(raw.get("token_out"))
    amount_in = _positive_int(raw.get("amount_in"))
    min_out = _positive_int(raw.get("min_out"))
    if not all((venue, token_in, token_out, amount_in, min_out)):
        return None
    return RouteLeg(
        dex=dex,
        venue=venue,
        token_in=token_in,
        token_out=token_out,
        amount_in=str(amount_in),
        min_out=str(min_out),
        data=str(raw.get("data") or raw.get("aux") or ""),
    )


def _validated_legs(raw_legs: Any) -> List[RouteLeg] | None:
    if not isinstance(raw_legs, list) or not raw_legs:
        return None
    legs: List[RouteLeg] = []
    for raw in raw_legs:
        leg = _validated_leg(raw)
        if leg is None:
            return None
        legs.append(leg)
    return legs


def _context_basics(context: Mapping[str, Any]) -> dict[str, Any] | None:
    provider = normalize_flashloan_provider(str(context.get("provider") or ""))
    if not is_executable_flashloan_provider(provider):
        return None
    borrow_token = _address(context.get("borrow_token"))
    profit_to = _address(context.get("profit_to"))
    amount_borrow = _positive_int(context.get("amount_borrow"))
    expected_profit_raw = _positive_int(context.get("expected_profit_raw"))
    if not borrow_token or not profit_to or amount_borrow is None or expected_profit_raw is None:
        return None
    return {
        "provider": provider,
        "borrow_token": borrow_token,
        "profit_to": profit_to,
        "amount_borrow": amount_borrow,
        "expected_profit_raw": expected_profit_raw,
    }


def _context_route(context: Mapping[str, Any], basics: Mapping[str, Any]) -> tuple[List[RouteLeg], str] | None:
    legs = _validated_legs(context.get("legs"))
    if legs is None or legs[0].token_in.lower() != str(basics["borrow_token"]).lower():
        return None
    if int(legs[0].amount_in) != int(basics["amount_borrow"]):
        return None
    route_id = route_id_hex(
        [
            EncLeg(
                dex=leg.dex,
                venue=leg.venue,
                token_in=leg.token_in,
                token_out=leg.token_out,
                aux=leg.data or "0x",
            )
            for leg in legs
        ]
    )
    return legs, route_id


def _simulation_gate(context: Mapping[str, Any]) -> dict[str, Any] | None:
    gate = validate_deterministic_simulation_evidence(context.get("simulation_evidence"))
    if gate.get("ok") is not True:
        return None
    if float(gate.get("expected_realized_profit_usd") or 0.0) <= 0.0:
        return None
    return dict(gate)


def _simulation_route_economics(
    context: Mapping[str, Any], legs: List[RouteLeg]
) -> tuple[float, float] | None:
    """Derive only the USD notional/validated route size proven by simulation inputs.

    Flash-loan borrow capacity is not Treasury/Prime capital. For the executable-edge
    objective we therefore use the simulation's explicitly priced input notional as
    the capital-efficiency denominator. Executable depth is the conservative minimum
    USD size of the validated route legs; it is a proven executable-size lower bound,
    not an inferred pool-capacity claim.
    """
    request = context.get("simulation_request")
    if not isinstance(request, Mapping):
        return None
    scenarios = request.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return None
    observation = scenarios[0].get("economic_observation") if isinstance(scenarios[0], Mapping) else None
    if not isinstance(observation, Mapping):
        return None
    assets = observation.get("assets")
    if not isinstance(assets, list) or not assets:
        return None
    prices: dict[str, tuple[int, float]] = {}
    for asset in assets:
        if not isinstance(asset, Mapping):
            return None
        address = str(asset.get("address") or "")
        try:
            decimals = int(asset.get("decimals"))
            price_usd = float(asset.get("price_usd"))
        except (TypeError, ValueError, OverflowError):
            return None
        if not address or decimals < 0 or decimals > 255 or price_usd <= 0.0:
            return None
        if address.lower() in prices:
            return None
        prices[address.lower()] = (decimals, price_usd)

    def _usd(token: str, raw_amount: str) -> float | None:
        priced = prices.get(str(token or "").lower())
        if priced is None:
            return None
        decimals, price = priced
        try:
            amount = int(str(raw_amount))
        except (TypeError, ValueError, OverflowError):
            return None
        if amount <= 0:
            return None
        value = (float(amount) / (10 ** decimals)) * price
        return value if value > 0.0 else None

    capital_required_usd = _usd(str(legs[0].token_in), legs[0].amount_in)
    if capital_required_usd is None:
        return None
    route_sizes = [_usd(str(leg.token_in), leg.amount_in) for leg in legs]
    if any(value is None for value in route_sizes):
        return None
    executable_depth_usd = min(float(value) for value in route_sizes if value is not None)
    return float(capital_required_usd), float(executable_depth_usd)


def _calldata_contract_check(*, basics: Mapping[str, Any], legs: List[RouteLeg]) -> bool:
    try:
        build_execute_calldata(
            provider=str(basics["provider"]),
            borrow_token=str(basics["borrow_token"]),
            amount_borrow=int(basics["amount_borrow"]),
            min_profit=1,
            profit_to=str(basics["profit_to"]),
            deadline=1,
            legs=[
                {
                    "dex": leg.dex,
                    "venue": leg.venue,
                    "token_in": leg.token_in,
                    "token_out": leg.token_out,
                    "min_out": int(leg.min_out),
                    "aux": leg.data or "0x",
                }
                for leg in legs
            ],
        )
    except (TypeError, ValueError, KeyError):
        return False
    return True


def _validated_context(context: Any) -> tuple[dict[str, Any], List[RouteLeg], dict[str, Any]] | None:
    if not isinstance(context, Mapping):
        return None
    basics = _context_basics(context)
    if basics is None:
        return None
    routed = _context_route(context, basics)
    if routed is None:
        return None
    legs, route_id = routed
    gate = _simulation_gate(context)
    if gate is None or not _calldata_contract_check(basics=basics, legs=legs):
        return None
    route_economics = _simulation_route_economics(context, legs)
    if route_economics is None:
        return None
    capital_required_usd, executable_depth_usd = route_economics
    normalized = dict(basics)
    normalized["route_id"] = route_id
    normalized["capital_required_usd"] = capital_required_usd
    normalized["executable_depth_usd"] = executable_depth_usd
    return normalized, legs, gate


def _candidate_metadata(
    candidate: Any,
    context: Mapping[str, Any],
    normalized: Mapping[str, Any],
    gate: Mapping[str, Any],
    provider: str,
) -> dict[str, Any]:
    metadata = getattr(candidate, "metadata", {})
    tx_hash = str(metadata.get("tx_hash") or "") if isinstance(metadata, Mapping) else ""
    return {
        "strategy_family": "flash_arb",
        "route_family": "flash_arb",
        "capital_source": "flashloan",
        "flash_provider": provider,
        "flash_providers": [provider],
        "flash_arb_context": dict(context),
        "mev_origin": {
            "engine_type": "mev_search",
            "tx_hash": tx_hash,
        },
        "simulation_evidence": dict(context.get("simulation_evidence") or {}),
        "simulation_gate": dict(gate),
        "capital_required_usd": float(normalized["capital_required_usd"]),
        "requested_notional_usd": float(normalized["capital_required_usd"]),
        "executable_depth_usd": float(normalized["executable_depth_usd"]),
        "economics_status": "simulation_backed",
        "economics_source": "deterministic_fork_simulation",
        "private_send_preference": True,
        "source_policy_eligibility": str(getattr(candidate, "policy_eligibility", "observe_only") or "observe_only"),
        "source_lifecycle_eligibility": str(getattr(candidate, "lifecycle_eligibility", "observe_only") or "observe_only"),
    }


def _build_flash_arb_opportunity(
    candidate: Any,
    context: Mapping[str, Any],
    normalized: Mapping[str, Any],
    legs: List[RouteLeg],
    gate: Mapping[str, Any],
) -> Opportunity:
    metadata = getattr(candidate, "metadata", {})
    tx_hash = str(metadata.get("tx_hash") or "") if isinstance(metadata, Mapping) else ""
    opportunity_id = f"mev-flash-arb:{tx_hash}" if tx_hash else f"mev-flash-arb:{normalized['route_id']}"
    expected_profit = float(gate["expected_realized_profit_usd"])
    return Opportunity(
        id=opportunity_id,
        chain=str(getattr(candidate, "chain", "ethereum") or "ethereum"),
        strategy="flash_arb",
        expected_profit_raw=str(normalized["expected_profit_raw"]),
        expected_profit_usd=str(expected_profit),
        route=Route(legs=legs),
        min_outs=[leg.min_out for leg in legs],
        route_id=str(normalized["route_id"]),
        can_execute=False,
        created_at_ms=0,
        meta=_candidate_metadata(candidate, context, normalized, gate, str(normalized["provider"])),
    )


def opportunity_from_engine_candidate(candidate: Any) -> Opportunity | None:
    """Convert only an explicitly validated MEV flash-arb context.

    The adapter is a translation boundary, not an authority. It refuses to
    manufacture routes, prices, borrow amounts, providers, or economics from
    mempool observations alone.
    """
    if str(getattr(candidate, "engine_type", "") or "") != "mev_search":
        return None
    metadata = getattr(candidate, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    context = metadata.get("flash_arb_context")
    validated = _validated_context(context)
    if validated is None:
        return None
    normalized, legs, gate = validated
    return _build_flash_arb_opportunity(candidate, context, normalized, legs, gate)


def opportunities_from_engine_state(items: Iterable[Any], admissions: Iterable[Any]) -> List[Opportunity]:
    """Return only MEV candidates that passed the existing engine admission gate."""
    rows = list(items or [])
    admission_rows = list(admissions or [])
    out: List[Opportunity] = []
    for row, admission in zip(rows, admission_rows):
        if not bool(getattr(admission, "allowed", False)):
            continue
        opportunity = opportunity_from_engine_candidate(row)
        if opportunity is not None:
            out.append(opportunity)
    return out
