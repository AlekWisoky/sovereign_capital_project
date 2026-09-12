from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

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


def _fingerprint(contract: InstitutionalSizingContract, approved: float, constraints: tuple[str, ...]) -> str:
    payload: dict[str, Any] = {
        "contract": contract.to_dict(),
        "approved_notional_usd": round(approved, 8),
        "constraints_applied": constraints,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "size-" + hashlib.sha256(encoded).hexdigest()[:24]


def calculate_institutional_size(contract: InstitutionalSizingContract) -> SizingDecision:
    """Calculate approved USD notional from already-authoritative inputs.

    This pure boundary never calls execution, governance, settlement, Treasury,
    or Internal Prime mutation methods and does not alter V1 flashloan sizing.
    Raw-unit conversion is deferred until final quote/requote because price and
    token-decimal data are not part of the institutional contract.
    """
    valid, errors = contract.validate()
    if not valid:
        raise ValueError("institutional_sizing_contract_invalid:" + ",".join(errors))

    requested = float(contract.requested_notional_usd)
    if requested <= 0.0:
        constraints = ("requested_notional",)
        return SizingDecision(
            sizing_id=_fingerprint(contract, 0.0, constraints),
            approved_notional_usd=0.0,
            approved_borrow_amount_raw=None,
            constraints_applied=constraints,
            downsize_reasons=("requested_notional_non_positive",),
            capital_utilization=0.0,
        )

    caps: list[tuple[str, float]] = [("requested_notional", requested)]

    # Wealth-goal posture is a bounded sizing modifier, never admission.
    goal = contract.wealth_goal
    commitment_factor = max(0.70, float(goal.capital_commitment_pct) / 30.0)
    wealth_cap = requested * max(0.0, float(goal.aggressiveness_cap)) * commitment_factor
    _add_cap(caps, "wealth_goal_aggressiveness", wealth_cap)

    capital = contract.capital
    if capital.deployable_usd is not None:
        _add_cap(
            caps,
            "capital_engine_deployable_pct",
            float(capital.deployable_usd) * max(0.0, float(contract.governance.max_deployable_pct)),
        )
    _add_cap(caps, "drawdown_buffer", capital.drawdown_buffer_usd)

    if capital.prime_capacity_usd is not None:
        remaining_prime = (
            float(capital.prime_capacity_usd) * max(0.0, 1.0 - float(capital.prime_utilization))
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
            max(0.0, float(capital.family_cap_usd) - float(capital.prime_family_exposure_usd)),
        )

    # A missing execution-evidence score is conservatively non-sizeable; no
    # new numeric threshold is invented here. Existing admission remains the
    # permission authority and this kernel only answers how much.
    execution = contract.execution
    if execution.latency_pressure >= 1.0 or execution.freshness_score <= 0.0:
        caps.append(("execution_realism", 0.0))
    if execution.simulation_confidence <= 0.0 or execution.endpoint_quality <= 0.0:
        caps.append(("execution_evidence", 0.0))

    approved = max(0.0, min(value for _, value in caps))
    constraints = tuple(label for label, _ in caps)
    downsize_reasons = tuple(label for label, value in caps if value < requested - 1e-9)

    utilization = 0.0
    if capital.deployable_usd is not None and float(capital.deployable_usd) > 0.0:
        utilization = approved / float(capital.deployable_usd)

    return SizingDecision(
        sizing_id=_fingerprint(contract, approved, constraints),
        approved_notional_usd=round(approved, 8),
        approved_borrow_amount_raw=None,
        constraints_applied=constraints,
        downsize_reasons=downsize_reasons,
        capital_utilization=round(utilization, 8),
    )
