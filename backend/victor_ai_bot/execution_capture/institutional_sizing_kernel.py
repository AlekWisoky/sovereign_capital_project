from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping

from .b4_quote_units import (
    QuoteUnitSizingError,
    quote_context_from_mapping,
    raw_units_to_usd_notional,
    usd_notional_to_raw_units,
    validate_quote_context,
)
from .institutional_sizing import InstitutionalSizingContract


@dataclass(frozen=True)
class SizingDecision:
    """Deterministic sizing result downstream of canonical admission."""

    sizing_id: str
    approved_notional_usd: float
    approved_borrow_amount_raw: int | None
    constraints_applied: tuple[str, ...]
    downsize_reasons: tuple[str, ...]
    capital_utilization: float


def _add_cap(caps: list[tuple[str, float]], label: str, value: float | None) -> None:
    if value is None:
        return
    try:
        number = float(value)
    except (TypeError, ValueError):
        return
    if math.isfinite(number) and number >= 0.0:
        caps.append((label, number))


def _fingerprint(
    contract: InstitutionalSizingContract,
    approved: float,
    constraints: tuple[str, ...],
    raw_units: int | None = None,
    quote: Mapping[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "contract": contract.to_dict(),
        "approved_notional_usd": round(approved, 8),
        "constraints_applied": constraints,
        "approved_borrow_amount_raw": raw_units,
        "quote": quote_context_from_mapping(quote),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return "size-" + hashlib.sha256(encoded).hexdigest()[:24]


def calculate_institutional_size(
    contract: InstitutionalSizingContract,
    *,
    final_quote: Mapping[str, Any] | None = None,
) -> SizingDecision:
    """Calculate approved notional and, when quoted, the final raw-unit amount.

    The USD constraint calculation remains deterministic and authority-free.
    Raw-unit conversion is permitted only with an explicit final quote carrying
    positive asset price and token decimals. The conversion floors raw units,
    then re-values those units at the same quote so a raw-unit hard cap cannot
    silently exceed the approved economic notional.
    """
    valid, errors = contract.validate()
    if not valid:
        raise ValueError("institutional_sizing_contract_invalid:" + ",".join(errors))

    requested = float(contract.requested_notional_usd)
    if requested <= 0.0:
        constraints = ("requested_notional",)
        return SizingDecision(
            sizing_id=_fingerprint(contract, 0.0, constraints, quote=final_quote),
            approved_notional_usd=0.0,
            approved_borrow_amount_raw=None,
            constraints_applied=constraints,
            downsize_reasons=("requested_notional_non_positive",),
            capital_utilization=0.0,
        )

    caps: list[tuple[str, float]] = [("requested_notional", requested)]

    goal = contract.wealth_goal
    commitment_factor = max(0.70, float(goal.capital_commitment_pct) / 30.0)
    wealth_cap = (
        requested * max(0.0, float(goal.aggressiveness_cap)) * commitment_factor
    )
    _add_cap(caps, "wealth_goal_aggressiveness", wealth_cap)

    capital = contract.capital
    if capital.deployable_usd is not None:
        _add_cap(
            caps,
            "capital_engine_deployable_pct",
            float(capital.deployable_usd)
            * max(0.0, float(contract.governance.max_deployable_pct)),
        )
    if capital.drawdown_buffer_usd is not None and capital.deployable_usd is not None:
        _add_cap(
            caps,
            "capital_after_drawdown_buffer",
            max(0.0, float(capital.deployable_usd) - float(capital.drawdown_buffer_usd)),
        )

    if capital.prime_capacity_usd is not None:
        remaining_prime = (
            float(capital.prime_capacity_usd)
            * max(0.0, 1.0 - float(capital.prime_utilization))
            - float(capital.prime_reserved_usd)
        )
        _add_cap(caps, "internal_prime_remaining_capacity", remaining_prime)

    liquidity = contract.liquidity
    _add_cap(caps, "liquidity_available", liquidity.available_usd)
    _add_cap(caps, "pool_depth", liquidity.depth_usd)
    _add_cap(caps, "pool_depth_cap", liquidity.pool_depth_cap_usd)
    _add_cap(caps, "provider_capacity", liquidity.provider_capacity_usd)
    _add_cap(caps, "route_capacity", liquidity.route_capacity_usd)

    if capital.family_cap_usd is not None:
        _add_cap(
            caps,
            "family_cap",
            max(
                0.0,
                float(capital.family_cap_usd)
                - float(capital.prime_family_exposure_usd),
            ),
        )

    economics = contract.economics
    economic_viability = True
    if economics.expected_net_profit_usd is None:
        economic_viability = False
    else:
        if float(economics.expected_net_profit_usd) < float(economics.min_profit_usd):
            economic_viability = False
        if float(economics.min_profit_bps) > 0.0:
            expected_bps = float(economics.expected_net_profit_usd) / requested * 10_000.0
            if expected_bps < float(economics.min_profit_bps):
                economic_viability = False
    if not economic_viability:
        caps.append(("expected_economics_viability", 0.0))

    # p_success and margin thresholds remain owned by canonical admission.
    constraints_without_cap = ("p_success_validated", "margin_validated")

    execution = contract.execution
    if execution.latency_pressure >= 1.0 or execution.freshness_score <= 0.0:
        caps.append(("execution_realism", 0.0))
    if execution.simulation_confidence <= 0.0 or execution.endpoint_quality <= 0.0:
        caps.append(("execution_evidence", 0.0))

    approved = max(0.0, min(value for _, value in caps))
    constraints = tuple(label for label, _ in caps) + constraints_without_cap
    downsize_reasons = tuple(
        label for label, value in caps if value < requested - 1e-9
    )

    raw_units: int | None = None
    if final_quote is not None:
        quote = quote_context_from_mapping(final_quote)
        quote_valid, quote_errors = validate_quote_context(quote)
        if not quote_valid:
            raise ValueError("final_quote_invalid:" + ",".join(quote_errors))
        try:
            raw_units = usd_notional_to_raw_units(
                approved,
                asset_price_usd=quote["asset_price_usd"],
                asset_decimals=int(quote["asset_decimals"]),
            )
            max_raw = int(contract.max_borrow_amount_wei or 0)
            if max_raw > 0 and raw_units > max_raw:
                raw_units = max_raw
                constraints = constraints + ("max_borrow_amount_raw",)
                downsize_reasons = downsize_reasons + ("max_borrow_amount_raw",)
                approved = raw_units_to_usd_notional(
                    raw_units,
                    asset_price_usd=quote["asset_price_usd"],
                    asset_decimals=int(quote["asset_decimals"]),
                )
        except QuoteUnitSizingError as exc:
            raise ValueError(f"final_quote_invalid:{exc}") from exc

    utilization = 0.0
    if capital.deployable_usd is not None and float(capital.deployable_usd) > 0.0:
        utilization = approved / float(capital.deployable_usd)

    return SizingDecision(
        sizing_id=_fingerprint(
            contract,
            approved,
            constraints,
            raw_units=raw_units,
            quote=final_quote,
        ),
        approved_notional_usd=round(approved, 8),
        approved_borrow_amount_raw=raw_units,
        constraints_applied=constraints,
        downsize_reasons=downsize_reasons,
        capital_utilization=round(utilization, 8),
    )
