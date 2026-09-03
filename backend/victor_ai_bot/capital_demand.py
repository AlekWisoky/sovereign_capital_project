from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CapitalDemand:
    """Canonical capital demand carried from decision through learning.

    Monetary values use USD micro-units so the decision record is deterministic.
    The fields distinguish requested capital from the amount actually authorized
    and ultimately deployed; OMAR never grants authority by populating this model.
    """

    requested_usd_micro: int = 0
    authorized_usd_micro: int = 0
    deployed_usd_micro: int = 0
    authority_source: str = ""
    capital_source: str = ""
    goal_posture: str = ""
    authorization_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _usd_micro(mapping: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return _safe_int(mapping.get(key))
    for key in keys:
        if key.endswith("_usd_micro"):
            continue
        if key in mapping and mapping.get(key) not in (None, ""):
            return _safe_int(float(mapping.get(key) or 0) * 1_000_000)
    return 0


def capital_demand_from_mapping(value: Any) -> CapitalDemand:
    """Normalize capital-demand facts from decision/admission/execution metadata."""
    root = _safe_dict(value)
    admission = _safe_dict(root.get("capitalAdmission"))
    if not admission:
        admission = _safe_dict(root.get("capital_admission"))
    details = _safe_dict(admission.get("details"))
    if not details:
        details = _safe_dict(root.get("details"))
    preview = _safe_dict(details.get("internalPrimePreview"))
    authority = _safe_dict(root.get("capitalAuthority"))
    goal = _safe_dict(root.get("wealth_goal")) or _safe_dict(root.get("wealthGoal"))

    requested = _usd_micro(
        root,
        "requested_usd_micro",
        "requestedUsdMicro",
        "requestedNotionalUsdMicro",
    )
    if requested == 0:
        requested = _usd_micro(
            admission,
            "requested_usd_micro",
            "requestedUsdMicro",
            "requested_notional_usd_micro",
        )
    if requested == 0:
        requested = _safe_int(float(details.get("requestedNotionalUsd") or 0) * 1_000_000)

    authorized = _usd_micro(
        root,
        "authorized_usd_micro",
        "authorizedUsdMicro",
        "authorizedNotionalUsdMicro",
    )
    if authorized == 0:
        authorized = _usd_micro(
            admission,
            "authorized_usd_micro",
            "authorizedUsdMicro",
            "authorized_notional_usd_micro",
        )
    if authorized == 0 and bool(admission.get("allowed", False)):
        authorized = requested
    if authorized == 0:
        authorized = _safe_int(float(preview.get("authorizedNotionalUsd") or 0) * 1_000_000)

    deployed = _usd_micro(
        root,
        "deployed_usd_micro",
        "deployedUsdMicro",
        "deployedNotionalUsdMicro",
        "actual_deployed_usd_micro",
    )
    if deployed == 0:
        deployed = _safe_int(float(root.get("deployedNotionalUsd") or 0) * 1_000_000)

    return CapitalDemand(
        requested_usd_micro=requested,
        authorized_usd_micro=min(authorized, requested) if requested else authorized,
        deployed_usd_micro=min(deployed, authorized) if authorized else deployed,
        authority_source=str(
            root.get("authority_source")
            or root.get("authoritySource")
            or authority.get("source")
            or authority.get("authority_source")
            or ""
        ),
        capital_source=str(
            root.get("capital_source")
            or root.get("capitalSource")
            or admission.get("capital_source")
            or admission.get("capitalSource")
            or ""
        ),
        goal_posture=str(
            root.get("goal_posture")
            or root.get("goalPosture")
            or goal.get("risk_tolerance")
            or goal.get("riskTolerance")
            or ""
        ),
        authorization_reason=str(
            root.get("authorization_reason")
            or root.get("authorizationReason")
            or admission.get("reason_code")
            or admission.get("reasonCode")
            or ""
        ),
    )
