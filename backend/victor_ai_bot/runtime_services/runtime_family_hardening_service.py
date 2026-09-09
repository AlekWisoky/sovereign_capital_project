from __future__ import annotations

from typing import Any, Dict

from .family_hardening_service import FamilyHardeningService as _FamilyHardeningService


class RuntimeFamilyHardeningService(_FamilyHardeningService):
    """Runtime-safe family hardening view that avoids launch/fund summary recursion."""

    @staticmethod
    def _context(runtime: Any) -> Dict[str, Any]:
        # Family hardening is itself part of the fund summary. Calling
        # runtime.fund_summary_state() here re-enters FundService.summary(),
        # which asks for family hardening again and can deadlock a TestClient
        # request. Build only the non-recursive context required by readiness.
        stage = "internal_capital"
        try:
            snapshot = (
                runtime._cc.snapshot()
                if getattr(runtime, "_cc", None) is not None
                and hasattr(runtime._cc, "snapshot")
                else {}
            )
            stage = str((snapshot or {}).get("fundStage") or stage)
        except (AttributeError, KeyError, TypeError, ValueError):
            pass

        try:
            capital_state = (
                runtime.capital_engine_state()
                if hasattr(runtime, "capital_engine_state")
                else {}
            )
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            capital_state = {}
        try:
            internal_prime = (
                runtime.internal_prime_state()
                if hasattr(runtime, "internal_prime_state")
                else {}
            )
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            internal_prime = {}
        try:
            drawdown = (
                runtime.drawdown_state()
                if hasattr(runtime, "drawdown_state")
                else {}
            )
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            drawdown = {}
        try:
            kill_switch = (
                runtime.kill_switch_state()
                if hasattr(runtime, "kill_switch_state")
                else {}
            )
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            kill_switch = {}

        fund_summary = {
            "fundStage": stage,
            "capitalReady": bool(capital_state.get("capital_engine")) if isinstance(capital_state, dict) else False,
            "internalPrimeReady": bool((internal_prime or {}).get("stateReady", True)),
            "privateRoutingReady": True,
            # Do not consult this service's own status while it is being computed.
            "familyHardeningStatus": "ok",
            "familyHardeningReasonCodes": [],
            "drawdownState": drawdown,
            "killSwitch": kill_switch,
        }
        return {
            "stage": stage,
            "scorecards": (
                runtime.strategy_scorecards_state()
                if hasattr(runtime, "strategy_scorecards_state")
                else {"families": []}
            ),
            "engine_state": runtime.engine_state() if hasattr(runtime, "engine_state") else {},
            "telemetry": (
                runtime.telemetry_summary() if hasattr(runtime, "telemetry_summary") else {}
            ),
            "calibration": (
                runtime.execution_calibration_state()
                if hasattr(runtime, "execution_calibration_state")
                else {}
            ),
            "fund_summary": fund_summary,
            "active_families": list(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "active_families",
                    [],
                )
                or []
            ),
            "family_states": dict(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "family_states",
                    {},
                )
                or {}
            ),
            "exploration_budget": dict(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "exploration_budget",
                    {},
                )
                or {}
            ),
            "capital_state": capital_state,
        }