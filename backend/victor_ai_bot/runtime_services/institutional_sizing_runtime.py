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

    @staticmethod
    def _capital_state(runtime: Any) -> dict[str, Any]:
        try:
            return (
                dict(runtime.capital_engine_state() or {})
                if hasattr(runtime, "capital_engine_state")
                else {}
            )
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            return {}

    @staticmethod
    def _prime_state(runtime: Any) -> dict[str, Any]:
        prime = getattr(runtime, "_internal_prime", None)
        if prime is None:
            return {}
        try:
            if hasattr(prime, "state"):
                return dict(prime.state() or {})
            if hasattr(prime, "snapshot"):
                return dict(prime.snapshot() or {})
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            pass
        return {}

    @staticmethod
    def _wealth_goal_state(runtime: Any) -> dict[str, Any]:
        wealth = getattr(runtime, "_wealth_goal_service", None)
        if wealth is None:
            return {}
        try:
            if hasattr(wealth, "state"):
                return dict(wealth.state() or {})
            if hasattr(wealth, "snapshot"):
                return dict(wealth.snapshot() or {})
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            pass
        return {}

    @staticmethod
    def _capture_context(
        opp: Any,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        meta = (
            dict(getattr(opp, "meta", {}) or {})
            if isinstance(getattr(opp, "meta", None), dict)
            else {}
        )
        capture = (
            dict(meta.get("capture") or {})
            if isinstance(meta.get("capture"), dict)
            else {}
        )
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
        return meta, capture_metadata, endpoint

    @staticmethod
    def _economics(opp: Any, result: Any, meta: dict[str, Any]) -> dict[str, Any]:
        economics = (
            dict(meta.get("profitability") or {})
            if isinstance(meta.get("profitability"), dict)
            else {}
        )
        if not economics:
            try:
                from ..profitability_state import profitability_state_view

                economics = dict(profitability_state_view(opp) or {})
            except (AttributeError, KeyError, TypeError, ValueError):
                economics = {}

        projected_edge = getattr(result, "projected_realized_edge_usd", None)
        confidence = getattr(result, "confidence", None)
        margin_ratio = meta.get("margin_ratio")
        if "expected_net_profit_usd" not in economics and projected_edge is not None:
            economics["expected_net_profit_usd"] = projected_edge
        if "success_probability" not in economics and confidence is not None:
            economics["success_probability"] = confidence
        if "margin_ratio" not in economics and margin_ratio is not None:
            economics["margin_ratio"] = margin_ratio
        return economics

    @staticmethod
    def _governance(runtime: Any, result: Any) -> dict[str, Any]:
        execution = getattr(getattr(runtime, "cfg", None), "execution", None)
        return {
            "admitted": bool(result.allowed),
            "reason_code": str(result.reason_code or ""),
            "strategy_family": str(result.strategy_family or ""),
            "capital_source": str(result.capital_source or ""),
            "live_authority": bool(getattr(execution, "live_authority", False)),
            "execution_allowed": bool(result.allowed),
        }

    def _institutional_record(
        self, runtime: Any, opp: Any, result: Any
    ) -> dict[str, Any]:
        meta, capture_metadata, endpoint = self._capture_context(opp)
        capital_state = self._capital_state(runtime)
        contract = build_institutional_sizing_contract(
            requested_notional_usd=float(result.requested_notional_usd or 0.0),
            strategy_family=str(result.strategy_family or ""),
            capital_source=str(result.capital_source or ""),
            capital_engine_state=capital_state,
            treasury_state=capital_state,
            internal_prime_state=self._prime_state(runtime),
            wealth_goal_state=self._wealth_goal_state(runtime),
            execution_capture=capture_metadata,
            latency_state=endpoint,
            economics=self._economics(opp, result, meta),
            governance=self._governance(runtime, result),
            settlement={},
        )
        valid, errors = contract.validate()
        return {
            "contract": contract.to_dict(),
            "valid": bool(valid),
            "errors": list(errors),
            "behavior_change": "none",
        }

    @staticmethod
    def _decorate_result(result: Any, record: dict[str, Any]) -> Any:
        details = dict(result.details or {})
        details["institutionalSizing"] = record
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

    def evaluate(self, runtime: Any, opp: Any, *, decision: Any | None = None):
        result = super().evaluate(runtime, opp, decision=decision)
        return self._decorate_result(
            result, self._institutional_record(runtime, opp, result)
        )
