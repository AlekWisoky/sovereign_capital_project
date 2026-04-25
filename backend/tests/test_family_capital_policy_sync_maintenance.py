from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.admission_service import AdmissionService
from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.treasury_service import TreasuryService
from victor_ai_bot.treasury.engine_capital_policy import engine_capital_limits


class _AdmissionRuntime:
    def __init__(self, family_targets: dict[str, float]):
        self._family_targets = family_targets
        self.cfg = SimpleNamespace(execution=SimpleNamespace(dry_run=False))
        self.scaled = []

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": dict(self._family_targets)}}

    def _scale_opportunity(self, opp, size_mult: float):
        self.scaled.append(size_mult)
        meta = dict(getattr(opp, "meta", {}) or {})
        meta["scaled_by"] = size_mult
        return SimpleNamespace(meta=meta)


class _CapitalSummaryRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum"),
            execution=SimpleNamespace(),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        self._ledger = SimpleNamespace(
            tail=lambda limit=50: [],
            transactions_tail=lambda limit=50: [],
            balances=lambda: {"USD": 0.0},
        )
        self._ledger_repo = None
        self._internal_prime = SimpleNamespace(snapshot=lambda: {"borrowedUsd": 0.0})
        self._treasury = SimpleNamespace(
            snapshot=lambda: {"ok": True, "enabled": True},
            cfg=SimpleNamespace(meta={"estimated_capital_wei": int(10e18)}),
        )
        self._bankroll = None
        self._last_operator_pnl_summary = {}
        self._last_settlement_sync = {}
        self._pnl = SimpleNamespace(summary=lambda window=50: {"total_realized_profit_after_gas_usd": 0.0})

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": int(10e18),
                "reserve_bankroll_wei": int(2e18),
                "experimental_bankroll_wei": 0,
                "drawdown_buffer_wei": 0,
                "treasury_offramp_wei": 0,
                "family_targets": {"flashloan_atomic": 0.6},
                "family_allocations_wei": {"flash_arb": int(6e18)},
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": int(4e18)},
            "reinvestment_policy": {},
        }

    def strategy_scorecards_state(self):
        return {
            "families": [
                {
                    "family": "flash_arb",
                    "gasEfficiency": 7.0,
                    "stability": 0.8,
                    "competitionPressure": 0.2,
                }
            ]
        }


class _Opportunity:
    def __init__(self, family: str):
        self.meta = {"strategy_family": family}


class _CaptureDecision:
    size_mult = 1.0

    @staticmethod
    def to_dict():
        return {"size_mult": 1.0}



def test_treasury_service_returns_family_cap_unknown_for_missing_family_target_under_available_truth():
    decision = TreasuryService().check_family_admission(
        capital_state={"capital_engine": {"family_targets": {"flashloan_atomic": 0.46}}},
        strategy_family="funding_arb",
        expected_value=25.0,
    )

    assert decision.admitted is False
    assert decision.reason == "family_cap_unknown"
    assert decision.limits["target_known"] is False
    assert decision.limits["requested_family"] == "funding_arb"



def test_treasury_service_and_engine_limits_resolve_flash_arb_alias_to_flashloan_atomic():
    capital_state = {
        "capital_engine": {
            "family_targets": {"flashloan_atomic": 0.46},
            "family_allocations_wei": {"flash_arb": int(4e18)},
            "deployable_bankroll_wei": int(10e18),
        }
    }

    decision = TreasuryService().check_family_admission(
        capital_state=capital_state,
        strategy_family="flash_arb",
        expected_value=10.0,
    )
    limits = engine_capital_limits(engine_type="unknown_engine", treasury_state=capital_state)

    assert decision.admitted is True
    assert decision.reason == "ok"
    assert decision.limits["resolved_target_key"] == "flashloan_atomic"
    assert limits["strategy_family"] == "flashloan_atomic"
    assert limits["resolved_target_key"] == "flashloan_atomic"
    assert limits["resolved_allocation_key"] == "flash_arb"
    assert limits["family_capital_usd"] == 4.0



def test_admission_service_family_budget_resolves_flash_arb_alias_before_scaling():
    runtime = _AdmissionRuntime({"flashloan_atomic": 0.5})
    opp = _Opportunity("flash_arb")

    scaled_opp, early_result = AdmissionService().apply_family_budget(
        runtime,
        opp,
        _CaptureDecision(),
        force_dry_run=False,
    )

    assert early_result is None
    assert runtime.scaled == [0.9]
    assert scaled_opp.meta["scaled_by"] == 0.9



def test_auxiliary_capital_summary_merges_target_and_allocation_aliases_into_one_family_plan_row():
    summary = AuxiliaryStateService().capital_summary(_CapitalSummaryRuntime())

    assert summary["familyCapitalPlanVersion"] == "family_capital_plan_v1"
    assert len(summary["familyCapitalPlan"]) == 1
    row = summary["familyCapitalPlan"][0]
    assert row["id"] == "flashloan_atomic"
    assert row["resolvedTargetKey"] == "flashloan_atomic"
    assert row["resolvedAllocationKey"] == "flash_arb"
    assert row["synchronizationStatus"] == "aligned"
    assert row["targetPct"] == 60.0
    assert row["capitalUsd"] == 6.0
