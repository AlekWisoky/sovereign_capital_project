from __future__ import annotations

"""Unit validation and physical-route identity for split economics.

Separates immutable route/cost evidence normalization from search/ranking logic.
"""

from fractions import Fraction
from typing import Any, Callable, Dict, List, Mapping, Sequence


SHARED_EXECUTION_OVERHEAD_GAS_UNITS = 180_000 + 90_000
_EXACT_BASE_L1_STATUSES = {"exact_calldata", "exact_calldata_cached"}


def _int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _curve_pool_key(venue: str) -> str | None:
    return f"curve|{venue}" if venue else None


def _balancer_pool_key(aux: str) -> str | None:
    return f"balancer|{aux}" if aux not in {"", "0x"} else None


def _router_pair_pool_key(protocol: str, venue: str, pair: str, aux: str) -> str | None:
    if not venue:
        return None
    if protocol in {"camelot_algebra", "camelot_v2", "constant_product"}:
        return f"{protocol}|{venue}|{pair}"
    if aux in {"", "0x"}:
        return None
    return f"{protocol}|{venue}|{pair}|{aux}"


def _pool_key_inputs(leg: Mapping[str, Any]) -> tuple[str, str, str, str] | None:
    protocol = str(leg.get("dex") or "").strip().lower()
    token_in = str(leg.get("token_in") or "").strip().lower()
    token_out = str(leg.get("token_out") or "").strip().lower()
    venue = str(leg.get("venue") or "").strip().lower()
    aux = str(leg.get("data") or leg.get("aux") or "0x").strip().lower()
    if not protocol or not token_in or not token_out or token_in == token_out:
        return None
    return protocol, venue, "|".join(sorted((token_in, token_out))), aux


def _curve_key_resolver(venue: str, pair: str, aux: str) -> str | None:
    return _curve_pool_key(venue)


def _balancer_key_resolver(venue: str, pair: str, aux: str) -> str | None:
    return _balancer_pool_key(aux)


def _router_fee_key_resolver(venue: str, pair: str, aux: str) -> str | None:
    return _router_pair_pool_key("univ3", venue, pair, aux)


def _slipstream_key_resolver(venue: str, pair: str, aux: str) -> str | None:
    return _router_pair_pool_key("slipstream", venue, pair, aux)


def _aerodrome_key_resolver(venue: str, pair: str, aux: str) -> str | None:
    return _router_pair_pool_key("aerodrome", venue, pair, aux)


def _camelot_algebra_key_resolver(venue: str, pair: str, aux: str) -> str | None:
    return _router_pair_pool_key("camelot_algebra", venue, pair, aux)


def _camelot_v2_key_resolver(venue: str, pair: str, aux: str) -> str | None:
    return _router_pair_pool_key("camelot_v2", venue, pair, aux)


def _constant_product_key_resolver(venue: str, pair: str, aux: str) -> str | None:
    return _router_pair_pool_key("constant_product", venue, pair, aux)


_POOL_KEY_RESOLVERS: Dict[str, Callable[[str, str, str], str | None]] = {
    "curve": _curve_key_resolver,
    "balancer": _balancer_key_resolver,
    "univ3": _router_fee_key_resolver,
    "slipstream": _slipstream_key_resolver,
    "aerodrome": _aerodrome_key_resolver,
    "camelot_algebra": _camelot_algebra_key_resolver,
    "camelot_v2": _camelot_v2_key_resolver,
    "constant_product": _constant_product_key_resolver,
}


def _generic_pool_key(protocol: str, venue: str, pair: str, aux: str) -> str | None:
    return f"{protocol}|{venue}|{pair}|{aux}" if venue else None


def _resolve_pool_key(
    protocol: str, venue: str, pair: str, aux: str
) -> str | None:
    resolver = _POOL_KEY_RESOLVERS.get(protocol)
    if resolver is None:
        return _generic_pool_key(protocol, venue, pair, aux)
    return resolver(venue, pair, aux)


def _leg_pool_key(leg: Mapping[str, Any]) -> str | None:
    """Return physical pool identity; never use router identity as profit evidence."""
    components = _pool_key_inputs(leg)
    if components is None:
        return None
    return _resolve_pool_key(*components)


def _candidate_numeric_values(candidate: Mapping[str, Any]) -> Dict[str, int] | None:
    keys = (
        ("amount", "amount_in"),
        ("gross", "gross_profit_wei"),
        ("fee", "flashloan_fee_wei"),
        ("gas_token", "gas_cost_profit_token_wei"),
        ("native_cost", "gas_cost_wei"),
        ("l2_gas", "gas_cost_l2_wei"),
        ("gas_units", "gas_units_estimate"),
        ("l1_fee", "base_l1_fee_wei"),
    )
    values: Dict[str, int] = {}
    for output_key, input_key in keys:
        value = _int(candidate.get(input_key))
        if value is None:
            return None
        values[output_key] = value
    return values


def _candidate_has_repay_and_gross_evidence(
    candidate: Mapping[str, Any], values: Mapping[str, int]
) -> bool:
    return bool(
        values["amount"] > 0
        and values["gross"] > 0
        and values["fee"] >= 0
        and candidate.get("repayment_valid") is True
    )


def _candidate_has_converted_gas_evidence(values: Mapping[str, int]) -> bool:
    return bool(
        values["gas_token"] > 0
        and values["native_cost"] > 0
        and values["l2_gas"] > 0
        and values["gas_units"] > SHARED_EXECUTION_OVERHEAD_GAS_UNITS
        and values["l1_fee"] >= 0
        and values["native_cost"] == values["l2_gas"] + values["l1_fee"]
    )


def _base_l1_fee_is_exact(candidate: Mapping[str, Any], chain_id: int) -> bool:
    return bool(
        int(chain_id) != 8453
        or str(candidate.get("base_l1_fee_status") or "") in _EXACT_BASE_L1_STATUSES
    )


def _route_token_pair_is_valid(
    token_in: str,
    token_out: str,
    expected_token_in: str,
) -> bool:
    return bool(token_in and token_out and token_in != token_out and token_in == expected_token_in)


def _route_protocol_has_pool(protocol: str, pool_key: str | None) -> bool:
    return bool(protocol and pool_key)


def _route_leg_identity(
    leg: Mapping[str, Any], expected_token_in: str
) -> Dict[str, str] | None:
    token_in = str(leg.get("token_in") or "").strip().lower()
    token_out = str(leg.get("token_out") or "").strip().lower()
    protocol = str(leg.get("dex") or "").strip().lower()
    pool_key = _leg_pool_key(leg)
    if not _route_token_pair_is_valid(token_in, token_out, expected_token_in):
        return None
    if not _route_protocol_has_pool(protocol, pool_key):
        return None
    venue = str(leg.get("venue") or "").strip().lower()
    return {
        "token_in": token_in,
        "token_out": token_out,
        "protocol": protocol,
        "pool_key": pool_key,
        "venue": venue,
        "directed_pair": f"{token_in}->{token_out}",
    }


def _collect_cycle_leg_identities(
    legs: Sequence[Mapping[str, Any]], borrow_token: str
) -> Dict[str, Any] | None:
    prior_token = borrow_token
    pool_keys: List[str] = []
    protocols: set[str] = set()
    routers: set[str] = set()
    directed_pairs: set[str] = set()
    for leg in legs:
        identity = _route_leg_identity(leg, prior_token)
        if identity is None:
            return None
        prior_token = identity["token_out"]
        pool_keys.append(identity["pool_key"])
        protocols.add(identity["protocol"])
        directed_pairs.add(identity["directed_pair"])
        if identity["venue"] and identity["protocol"] != "curve":
            routers.add(identity["venue"])
    if prior_token != borrow_token or len(pool_keys) != len(set(pool_keys)):
        return None
    return {
        "borrow_token": borrow_token,
        "pool_keys": set(pool_keys),
        "protocols": protocols,
        "routers": routers,
        "directed_pairs": directed_pairs,
    }


def _cycle_identity(
    legs: Sequence[Mapping[str, Any]], amount_in: int
) -> Dict[str, Any] | None:
    if len(legs) not in (2, 3):
        return None
    if _int(legs[0].get("amount_in")) != amount_in:
        return None
    borrow_token = str(legs[0].get("token_in") or "").strip().lower()
    if not borrow_token:
        return None
    return _collect_cycle_leg_identities(legs, borrow_token)


def _candidate_evidence_rank(row: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    """Prefer valid authoritative economics before larger diagnostic estimates."""
    return (
        int(bool(row.get("revalidated") and row.get("authoritative") and row.get("valid") and row.get("repayment_valid"))),
        int(bool(row.get("authoritative"))),
        int(bool(row.get("revalidated"))),
        int(row.get("single_route_net_wei") or 0),
        int(row.get("gross_profit_wei") or 0),
    )


def _candidate_costs_are_admissible(
    candidate: Mapping[str, Any], values: Mapping[str, int], chain_id: int
) -> bool:
    return bool(
        _candidate_has_repay_and_gross_evidence(candidate, values)
        and _candidate_has_converted_gas_evidence(values)
        and _base_l1_fee_is_exact(candidate, chain_id)
    )


def _normalize_candidate(
    candidate: Mapping[str, Any], *, chain_id: int
) -> Dict[str, Any] | None:
    route_id = str(candidate.get("route_id") or "")
    values = _candidate_numeric_values(candidate)
    if not route_id or values is None:
        return None
    if not _candidate_costs_are_admissible(candidate, values, int(chain_id)):
        return None
    legs = [dict(row) for row in candidate.get("legs", []) if isinstance(row, Mapping)]
    identity = _cycle_identity(legs, values["amount"])
    if identity is None:
        return None

    l2_price = max(1, (values["l2_gas"] + values["gas_units"] - 1) // values["gas_units"])
    conversion = Fraction(values["gas_token"], values["native_cost"])
    return {
        "route_id": route_id,
        "amount_in": values["amount"],
        "gross_profit_wei": values["gross"],
        "flashloan_fee_wei": values["fee"],
        "gas_cost_profit_token_wei": values["gas_token"],
        "gas_cost_wei": values["native_cost"],
        "gas_cost_l2_wei": values["l2_gas"],
        "gas_units_estimate": values["gas_units"],
        "gas_price_effective_wei": l2_price,
        "base_l1_fee_wei": values["l1_fee"],
        "base_l1_fee_status": str(candidate.get("base_l1_fee_status") or ""),
        "borrow_token": identity["borrow_token"],
        "legs": legs,
        "pool_keys": identity["pool_keys"],
        "protocols": identity["protocols"],
        "routers": identity["routers"],
        "directed_pairs": identity["directed_pairs"],
        "single_route_net_wei": values["gross"] - values["fee"] - values["gas_token"],
        "gas_token_per_native_wei": conversion,
        "revalidated": candidate.get("revalidated") is True,
        "authoritative": candidate.get("authoritative") is True,
        "valid": candidate.get("valid") is True,
        "repayment_valid": candidate.get("repayment_valid") is True,
    }
