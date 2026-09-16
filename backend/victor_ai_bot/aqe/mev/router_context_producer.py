from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ...calldata_builder import build_execute_calldata
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


def _uint_word(data: str, index: int) -> int | None:
    if not isinstance(data, str) or not data.startswith("0x"):
        return None
    raw = data[2:]
    start = index * 64
    end = start + 64
    if len(raw) < end:
        return None
    try:
        return int(raw[start:end], 16)
    except ValueError:
        return None


def _address_word(data: str, index: int) -> str | None:
    word = _uint_word(data, index)
    if word is None or word < 0 or word >= 1 << 160:
        return None
    return f"0x{word:040x}"


def decode_allowlisted_univ3_swap(tx: Mapping[str, Any], *, router: str) -> dict[str, Any] | None:
    """Decode only the supported UniV3 router call on the configured router.

    This is an observation/translation boundary. It does not infer pools,
    economics, flash-loan parameters, or execution authority from calldata.
    """
    if not isinstance(tx, Mapping):
        return None
    tx_to = _address(tx.get("to"))
    configured_router = _address(router)
    if not tx_to or not configured_router or tx_to.lower() != configured_router.lower():
        return None
    data = str(tx.get("input") or tx.get("data") or "")
    if not data.lower().startswith(_EXACT_INPUT_SINGLE_SELECTOR):
        return None
    if len(data) != 2 + 8 * 64 + 8:
        return None
    token_in = _address_word(data, 0)
    token_out = _address_word(data, 1)
    fee = _uint_word(data, 2)
    recipient = _address_word(data, 3)
    deadline = _uint_word(data, 4)
    amount_in = _uint_word(data, 5)
    amount_out_min = _uint_word(data, 6)
    sqrt_price_limit_x96 = _uint_word(data, 7)
    if not all((token_in, token_out, fee is not None, recipient, deadline is not None, amount_in, amount_out_min is not None, sqrt_price_limit_x96 is not None)):
        return None
    if not 0 < fee <= 1_000_000 or amount_in <= 0 or amount_out_min <= 0:
        return None
    if deadline <= 0:
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
        amount_in = str(getattr(leg, "amount_in", "") or "")
        min_out = str(getattr(leg, "min_out", "") or "")
        if dex not in {"univ3", "curve", "balancer"} or not all((venue, token_in, token_out)):
            return None
        try:
            amount_i = int(amount_in)
            min_o = int(min_out)
        except (TypeError, ValueError, OverflowError):
            return None
        if amount_i <= 0 or min_o <= 0:
            return None
        data = str(getattr(leg, "data", "") or "0x")
        out.append({
            "dex": dex,
            "venue": venue,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_i,
            "min_out": min_o,
            "aux": data,
        })
    return out


def _canonical_flash_arb_source(base_opportunities: Sequence[Any], observed: Mapping[str, Any]) -> Opportunity | None:
    """Select an already-created canonical arb opportunity; never invent a route."""
    token_in = str(observed["token_in"]).lower()
    token_out = str(observed["token_out"]).lower()
    amount_in = int(observed["amount_in"])
    for opportunity in list(base_opportunities or []):
        if str(getattr(opportunity, "strategy", "") or "") != "flash_arb":
            continue
        legs = _route_legs(opportunity)
        if not legs:
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
    """Produce canonical flash-arb context only from real bounded inputs.

    The canonical route comes from the existing arb-engine opportunity list.
    The router transaction is used only as a validated trigger/context anchor.
    Simulation input must be supplied by an existing simulation source; this
    function never fabricates a fork transaction, economics, or evidence.
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
    if not legs:
        return None
    amount_borrow = int(legs[0]["amount_in"])
    expected_profit_raw = int(str(getattr(opportunity, "expected_profit_raw", "0") or "0"))
    if amount_borrow <= 0 or expected_profit_raw <= 0:
        return None

    context: dict[str, Any] = {
        "strategy": "flash_arb",
        "tx_hash": observed["tx_hash"],
        "provider": normalized_provider,
        "borrow_token": legs[0]["token_in"],
        "profit_to": destination,
        "amount_borrow": amount_borrow,
        "expected_profit_raw": expected_profit_raw,
        "legs": legs,
        "observed_router_call": observed,
        "source_opportunity_id": str(getattr(opportunity, "id", "") or ""),
        "source_route_id": str(getattr(opportunity, "route_id", "") or ""),
    }

    if simulation_request is None:
        return None
    request = dict(simulation_request)
    transaction = request.get("transaction")
    scenarios = request.get("scenarios")
    if not isinstance(transaction, Mapping) or not isinstance(scenarios, list) or not scenarios:
        return None
    context["simulation_request"] = request
    return context
