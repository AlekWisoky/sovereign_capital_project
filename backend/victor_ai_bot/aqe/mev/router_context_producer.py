from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ...flashloan_providers import is_executable_flashloan_provider, normalize_flashloan_provider
from ...models import Opportunity


# Uniswap V3 SwapRouter exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))
_EXACT_INPUT_SINGLE_SELECTOR = "0x414bf389"


def _address(value: Any) -> str | None:
    text = str(value or "")
    if len(text) != 42 or not text.startswith("0x"):
        return None
    try:
        int(text[2:], 16)
    except ValueError:
        return None
    return text


def _uint_word(payload: str, index: int) -> int | None:
    if not isinstance(payload, str) or not payload.startswith("0x"):
        return None
    raw = payload[2:]
    start = index * 64
    end = start + 64
    if len(raw) < end:
        return None
    try:
        return int(raw[start:end], 16)
    except ValueError:
        return None


def _address_word(payload: str, index: int) -> str | None:
    word = _uint_word(payload, index)
    if word is None or word >= 1 << 160:
        return None
    return f"0x{word:040x}"


def decode_allowlisted_univ3_swap(tx: Mapping[str, Any], *, router: str) -> dict[str, Any] | None:
    """Decode only exactInputSingle on the configured UniV3 router."""
    if not isinstance(tx, Mapping):
        return None
    tx_to = _address(tx.get("to"))
    configured_router = _address(router)
    if not tx_to or not configured_router or tx_to.lower() != configured_router.lower():
        return None
    data = str(tx.get("input") or tx.get("data") or "")
    if not data.lower().startswith(_EXACT_INPUT_SINGLE_SELECTOR):
        return None
    payload = "0x" + data[10:]
    if len(payload) != 2 + 8 * 64:
        return None
    token_in = _address_word(payload, 0)
    token_out = _address_word(payload, 1)
    fee = _uint_word(payload, 2)
    recipient = _address_word(payload, 3)
    deadline = _uint_word(payload, 4)
    amount_in = _uint_word(payload, 5)
    amount_out_min = _uint_word(payload, 6)
    sqrt_price_limit_x96 = _uint_word(payload, 7)
    if not all((token_in, token_out, fee is not None, recipient, deadline is not None, amount_in, amount_out_min is not None, sqrt_price_limit_x96 is not None)):
        return None
    if not 0 < fee <= 1_000_000 or amount_in <= 0 or amount_out_min <= 0 or deadline <= 0:
        return None
    return {
        "protocol": "uniswap_v3",
        "function": "exactInputSingle",
        "router": configured_router,
        "token_in": token_in,
        "token_out": token_out,
        "fee": int(fee),
        "recipient": recipient,
        "deadline": int(deadline),
        "amount_in": int(amount_in),
        "amount_out_minimum": int(amount_out_min),
        "sqrt_price_limit_x96": int(sqrt_price_limit_x96),
        "tx_hash": str(tx.get("hash") or ""),
    }


def _route_legs(opportunity: Any) -> list[dict[str, Any]] | None:
    route = getattr(opportunity, "route", None)
    legs = getattr(route, "legs", None)
    if not isinstance(legs, Sequence) or not legs:
        return None
    out: list[dict[str, Any]] = []
    for leg in legs:
        dex = str(getattr(leg, "dex", "") or "")
        venue = _address(getattr(leg, "venue", ""))
        token_in = _address(getattr(leg, "token_in", ""))
        token_out = _address(getattr(leg, "token_out", ""))
        try:
            amount_in = int(str(getattr(leg, "amount_in", "") or ""))
            min_out = int(str(getattr(leg, "min_out", "") or ""))
        except (TypeError, ValueError, OverflowError):
            return None
        if dex not in {"univ3", "curve", "balancer"} or not all((venue, token_in, token_out)):
            return None
        if amount_in <= 0 or min_out <= 0:
            return None
        out.append({
            "dex": dex,
            "venue": venue,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_in,
            "min_out": min_out,
            "aux": str(getattr(leg, "data", "") or "0x"),
        })
    return out


def _canonical_flash_arb_source(base_opportunities: Sequence[Any], observed: Mapping[str, Any]) -> Opportunity | None:
    """Select an existing canonical arb route; never synthesize one."""
    token_in = str(observed["token_in"]).lower()
    token_out = str(observed["token_out"]).lower()
    amount_in = int(observed["amount_in"])
    for opportunity in list(base_opportunities or []):
        strategy = str(getattr(opportunity, "strategy", "") or "")
        if strategy != "flash_arb" and not strategy.startswith("two-leg:"):
            continue
        legs = _route_legs(opportunity)
        if not legs or len(legs) != 2:
            continue
        first = legs[0]
        if first["token_in"].lower() != token_in or first["token_out"].lower() != token_out:
            continue
        if int(first["amount_in"]) != amount_in:
            continue
        return opportunity
    return None


def produce_flash_arb_context_from_router(
    *,
    tx: Mapping[str, Any],
    router: str,
    base_opportunities: Sequence[Any],
    provider: str,
    profit_to: str,
    simulation_request: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build context from an allowlisted real router call and existing route.

    The route comes from the existing arb engine. Simulation input remains an
    explicit upstream dependency; this function never fabricates simulation,
    economics, provider, or execution authority.
    """
    observed = decode_allowlisted_univ3_swap(tx, router=router)
    if observed is None:
        return None
    opportunity = _canonical_flash_arb_source(base_opportunities, observed)
    if opportunity is None:
        return None
    normalized_provider = normalize_flashloan_provider(provider)
    destination = _address(profit_to)
    if not is_executable_flashloan_provider(normalized_provider) or not destination:
        return None
    legs = _route_legs(opportunity)
    if not legs or len(legs) != 2:
        return None
    try:
        expected_profit_raw = int(str(getattr(opportunity, "expected_profit_raw", "") or ""))
    except (TypeError, ValueError, OverflowError):
        return None
    if expected_profit_raw <= 0:
        return None
    context: dict[str, Any] = {
        "strategy": "flash_arb",
        "tx_hash": observed["tx_hash"],
        "provider": normalized_provider,
        "borrow_token": legs[0]["token_in"],
        "profit_to": destination,
        "amount_borrow": int(legs[0]["amount_in"]),
        "expected_profit_raw": expected_profit_raw,
        "legs": legs,
        "observed_router_call": observed,
        "source_opportunity_id": str(getattr(opportunity, "id", "") or ""),
        "source_route_id": str(getattr(opportunity, "route_id", "") or ""),
    }
    if simulation_request is None:
        return None
    request = dict(simulation_request)
    if not isinstance(request.get("transaction"), Mapping) or not isinstance(request.get("scenarios"), list) or not request.get("scenarios"):
        return None
    context["simulation_request"] = request
    return context
