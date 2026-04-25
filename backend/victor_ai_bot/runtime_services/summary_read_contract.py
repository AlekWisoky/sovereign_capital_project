from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from typing import Any, Dict, Mapping

from ..degraded_state_contract import contract_from_surface
from ..jsonsafe import to_json_safe

SUMMARY_READ_CONTRACT_VERSION = "canonical_summary_read_contract_v1"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _contract_reference(value: Any) -> Dict[str, Any]:
    payload = _safe_dict(value)
    if not payload:
        return {}
    if isinstance(payload.get("stateContract"), ABCMapping):
        payload = _safe_dict(payload.get("stateContract"))
    out: Dict[str, Any] = {}
    for key in (
        "contractVersion",
        "truthFamily",
        "readModel",
        "phase",
        "status",
        "reason_code",
        "degraded",
        "blocked",
        "denied",
        "sticky_cycle",
    ):
        if key in payload:
            out[key] = payload.get(key)
    return out


def build_summary_read_contract(
    *,
    family: str,
    payload: Mapping[str, Any] | None = None,
    capital_contract: Mapping[str, Any] | None = None,
    capital_policy: Mapping[str, Any] | None = None,
    source_contracts: Mapping[str, Any] | None = None,
    phase: str | None = None,
    read_model: str | None = None,
) -> Dict[str, Any]:
    surface = _safe_dict(payload)
    state_contract = contract_from_surface(
        surface,
        phase=str(phase or f"{family}_summary"),
        default_reason=str(surface.get("reason_code") or surface.get("error") or "ok"),
        sticky_cycle=True,
    )
    sources: Dict[str, Dict[str, Any]] = {}
    for name, value in _safe_dict(source_contracts).items():
        ref = _contract_reference(value)
        if ref:
            sources[str(name)] = ref
    return to_json_safe(
        {
            "ok": True,
            "contractVersion": SUMMARY_READ_CONTRACT_VERSION,
            "truthFamily": str(family or "summary"),
            "readModel": str(read_model or f"{family}_summary_projection_v1"),
            "synthesized": True,
            "capitalContractVersion": str(
                _safe_dict(capital_contract).get("contractVersion") or ""
            ),
            "capitalPolicyVersion": str(_safe_dict(capital_policy).get("contractVersion") or ""),
            "stateContract": state_contract,
            "sourceContracts": sources,
        }
    )
