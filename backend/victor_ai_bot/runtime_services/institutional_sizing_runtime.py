from __future__ import annotations

from typing import Any

from .capital_admission_service import CapitalAdmissionService
from ..execution_capture.institutional_sizing import build_institutional_sizing_contract


class InstitutionalSizingAdmissionService(CapitalAdmissionService):
    """Runtime adapter that materializes the Phase-B sizing contract.

    The existing CapitalAdmissionService remains authoritative for admission.
    This adapter only normalizes its already-computed inputs into the typed
    institutional contract; it does not re-run capital, family, wealth-goal,
    drawdown, or governance policy and it does not calculate a new size.
    """

    def evaluate(self, runtime: Any, opp: Any, *, decision: Any | None = None):
        result = super().evaluate(runtime, opp, decision=decision)
        details = dict(result.details or {})
        capital_state = (
            runtime.capital_engine_state()
            if hasattr(runtime, "capital_engine_state")
            else {}
        )
        prime_state = {}
        prime = getattr(runtime, "_internal_prime", None)
        if prime is not None:
            try:
                if hasattr(prime, "state"):
                    prime_state = dict(prime.state() or {})
                elif hasattr(prime, "snapshot"):
                    prime_state = dict(prime.snapshot() or {})
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                prime_state = {}

        wealth_goal_state = {}
        wealth = getattr(runtime, "_wealth_goal_service", None)
        if wealth is not None:
            try:
                if hasattr(wealth, "state"):
                    wealth_goal_state = dict(wealth.state() or {})
                elif hasattr(wealth, "snapshot"):
                    wealth_goal_state = dict(wealth.snapshot() or {})
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                wealth_goal_state = {}

        meta = (
            dict(getattr(opp, "meta", {}) or {})
            if isinstance(getattr(opp, "meta", None), dict)
            else {}
        )
        capture = dict(meta.get("capture") or {}) if isinstance(meta.get("capture"), dict) else {}
        capture_metadata = (
            dict(capture.get("metadata") or {})
            if isinstance(capture.get("metadata"), dict)
            else {}
        )
        endpoint = (
            dict(capture_metadata.get("endpoint_selection") or {})
            if isinstance(capture_metadata.get("endpoint_selection"), dict)
            else {}
        )
        economics = dict(meta.get("profitability") or {}) if isinstance(meta.get("profitability"), dict) else {}
        if not economics:
            try:
                from ..profitability_state import profitability_state_view

                economics = dict(profitability_state_view(opp) or {})
            except (AttributeError, KeyError, TypeError, ValueError):
                economics = {}
        economics.setdefault("expected_net_profit_usd", float(result.projected_realized_edge_usd or 0.0))
        economics.setdefault("success_probability", float(result.confidence or 0.0))
        economics.setdefault(
            "margin_ratio",
            float(meta.get("margin_ratio") or 0.0),
        )

        governance = {
            "admitted": bool(result.allowed),
            "reason_code": str(result.reason_code or ""),
            "strategy_family": str(result.strategy_family or ""),
            "capital_source": str(result.capital_source or ""),
            "live_authority": bool(
                getattr(
                    getattr(getattr(runtime, "cfg", None), "execution", None),
                    "live_authority",
                    False,
                )
            ),
            "execution_allowed": bool(result.allowed),
        }
        contract = build_institutional_sizing_contract(
            requested_notional_usd=float(result.requested_notional_usd or 0.0),
            strategy_family=str(result.strategy_family or ""),
            capital_source=str(result.capital_source or ""),
            capital_engine_state=capital_state,
            treasury_state=capital_state,
            internal_prime_state=prime_state,
            wealth_goal_state=wealth_goal_state,
            execution_capture=capture_metadata,
            latency_state=endpoint,
            economics=economics,
            governance=governance,
            settlement={},
        )
        valid, errors = contract.validate()
        details["institutionalSizing"] = {
            "contract": contract.to_dict(),
            "valid": bool(valid),
            "errors": list(errors),
            "behavior_change": "none",
        }
        return type(result)(
            allowed=result.allowed,
            reason_code=result.reason_code,
            strategy_family=result.strategy_family,
            capital_source=result.capital_source,
            requested_notional_usd=result.requested_notional_usd,
            projected_realized_edge_usd=result.projected_realized_edge_usd,
            confidence=result.confidence,
            details=details,
        )
