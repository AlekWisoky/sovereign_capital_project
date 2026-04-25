from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.internal_prime.allocator import InternalPrimeAllocator
from victor_ai_bot.internal_prime.contracts import PrimeBorrowRequest
from victor_ai_bot.runtime_services.capital_admission_service import CapitalAdmissionService
from victor_ai_bot.runtime_services.execution_service import ExecutionService


class _Leg:
    def __init__(self, *, token_in: str = "USDC", amount_in: str = "100", min_out: str = "120"):
        self.token_in = token_in
        self.amount_in = amount_in
        self.min_out = min_out


class _Route:
    def __init__(self):
        self.legs = [_Leg(), _Leg(token_in="WETH", amount_in="120", min_out="140")]


class _Opp:
    def __init__(self):
        self.id = "opp-1"
        self.route_id = "route-1"
        self.route = _Route()
        self.expected_profit_usd = 25.0
        self.capital_required_usd = 250_000.0
        self.meta = {"strategy_family": "flashloan_atomic", "route_family": "flashloan_atomic"}


class _RpcManager:
    def best_send(self):
        return "https://send"

    def best_private(self):
        return "https://private"

    def best_read(self):
        return "https://read"


def _runtime(
    *,
    capital_summary=None,
    capital_engine=None,
    internal_prime=None,
    capital_admission_service=None,
    fund_summary=None,
):
    return SimpleNamespace(
        cfg=SimpleNamespace(
            execution=SimpleNamespace(
                gas_mode="standard",
                send_mode="public",
                dry_run=False,
                governance=SimpleNamespace(enforce_on_auto=False),
                consensus=SimpleNamespace(enforce_on_auto=False),
                flashloan_fee_bps=9,
                gas_limit=200000,
            ),
            safety=SimpleNamespace(minProfitAbs=1, minProfitBps=0),
        ),
        metrics=SimpleNamespace(gas_mode="standard", send_mode="public"),
        rpc_manager=_RpcManager(),
        _cc=SimpleNamespace(snapshot=lambda: {"fundStage": "internal_capital"}),
        _capital_admission_service=capital_admission_service,
        _internal_prime=internal_prime,
        capital_engine_state=lambda: {
            "borrow_mult_target_cap": 1.4,
            "capital_engine": {
                "family_targets": {"flashloan_atomic": 0.35, "carry_trade": 0.20},
                **dict(capital_engine or {}),
            },
        },
        capital_truth=lambda: SimpleNamespace(
            capital_summary={
                "deployableUsd": 100_000.0,
                "navUsd": 250_000.0,
                "utilizationPct": 20.0,
                **dict(capital_summary or {}),
            }
        ),
        fund_summary_state=lambda: dict(fund_summary or {}),
        _consensus=None,
        _gov=None,
        _super=None,
    )


def test_internal_prime_preview_is_side_effect_free(tmp_path: Path):
    allocator = InternalPrimeAllocator(data_dir=str(tmp_path), chain="test")
    allocator.inventory.seed("USDC", 500_000.0)
    before = allocator.snapshot()
    req = PrimeBorrowRequest(
        family="carry_trade",
        capital_source="internal_prime",
        notional_usd=100_000.0,
        asset="USDC",
        horizon_minutes=60.0,
        confidence=0.92,
    )

    preview = allocator.preview(
        req,
        stage_policy={
            "stage": "internal_capital",
            "max_deployable_pct": 0.35,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 10_000_000.0,
            "min_confidence": 0.75,
        },
    )

    assert preview["allowed"] is True
    assert preview["preview"] is True
    assert allocator.snapshot() == before


def test_capital_admission_service_denies_internal_prime_when_preview_fails():
    service = CapitalAdmissionService()
    opp = _Opp()
    opp.meta["strategy_family"] = "carry_trade"
    opp.meta["route_family"] = "carry_trade"
    opp.meta["loan_source"] = "internal_prime"
    opp.capital_required_usd = 10_000.0
    decision = SimpleNamespace(expected_realized_value=12.0, success_probability=0.9, metadata={})
    runtime = _runtime(
        internal_prime=SimpleNamespace(
            preview=lambda req, stage_policy: {"allowed": False, "reason": "family_cap_exceeded"}
        )
    )

    result = service.evaluate(runtime, opp, decision=decision)

    assert result.allowed is False
    assert result.reason_code == "internal_prime:family_cap_exceeded"
    assert result.capital_source == "internal_prime"
    assert result.details["loanPolicy"]["allowed"] is True
    assert result.details["internalPrimePreview"]["reason"] == "family_cap_exceeded"


def test_capital_admission_service_derives_scaled_flashloan_notional_from_entry_notional():
    service = CapitalAdmissionService()
    opp = _Opp()
    opp.capital_required_usd = 0.0
    opp.meta["capital_required_usd"] = 0.0
    opp.meta["entry_notional_usd"] = 10_000.0
    opp.meta["unit_econ"] = {"entry_notional_usd_micro": "10000000000"}
    decision = SimpleNamespace(
        expected_realized_value=20.0,
        success_probability=0.92,
        size_mult=1.0,
        borrow_mult=2.0,
        metadata={
            "flashloan_resilience": {
                "sizing": {"allowed": True, "reason_codes": [], "borrow_mult": 2.0}
            }
        },
    )
    runtime = _runtime(capital_admission_service=service)

    result = service.evaluate(runtime, opp, decision=decision)

    assert result.allowed is False
    assert result.reason_code == "loan_policy:thin_after_borrow_cost"
    assert result.requested_notional_usd == 20_000.0
    assert result.details["baseNotionalUsd"] == 10_000.0
    assert result.details["notionalMultiplier"] == 2.0
    assert result.details["loanPolicy"]["borrowCostUsd"] == 18.0


def test_execution_service_prepare_auto_execution_blocks_on_capital_admission_failure():
    svc = ExecutionService()
    opp = _Opp()
    decision = SimpleNamespace(
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
        metadata={
            "execution_route_plan": {"executable": True, "selected_venues": ["uni"]},
            "flashloan_resilience": {
                "sizing": {"allowed": False, "reason_codes": ["provider_capacity"]}
            },
        },
    )
    runtime = _runtime(
        capital_admission_service=CapitalAdmissionService(),
    )

    result = svc.prepare_auto_execution(runtime, opp, bn=21, decision=decision)

    assert result.proceed is False
    assert result.blocked_result is not None
    assert result.blocked_result.reason == "capital_admission:flashloan_size_not_viable"
    assert result.metadata["capitalAdmission"]["reason_code"] == "flashloan_size_not_viable"
    assert result.opportunity.meta["capital_admission"]["capital_source"] == "flashloan"


def test_capital_admission_service_denies_flashloan_when_notional_truth_is_missing():
    service = CapitalAdmissionService()
    opp = _Opp()
    opp.capital_required_usd = 0.0
    opp.meta["capital_required_usd"] = 0.0
    opp.meta.pop("entry_notional_usd", None)
    opp.meta["unit_econ"] = {}
    decision = SimpleNamespace(
        expected_realized_value=12.0,
        success_probability=0.9,
        metadata={"flashloan_resilience": {"sizing": {"allowed": True}}},
    )
    runtime = _runtime(capital_admission_service=service)

    result = service.evaluate(runtime, opp, decision=decision)

    assert result.allowed is False
    assert result.reason_code == "flashloan_notional_unavailable"
    assert result.details["loanPolicy"]["allowed"] is False
    assert result.details["loanPolicy"]["strict"] is True
    assert result.details["notionalTruth"]["complete"] is False
    assert result.to_dict()["stateContract"]["reason_code"] == "flashloan_notional_unavailable"


def test_execution_service_prepare_auto_execution_blocks_when_flashloan_notional_truth_is_missing():
    svc = ExecutionService()
    opp = _Opp()
    opp.capital_required_usd = 0.0
    opp.meta["capital_required_usd"] = 0.0
    opp.meta["unit_econ"] = {}
    decision = SimpleNamespace(
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
        metadata={
            "execution_route_plan": {"executable": True, "selected_venues": ["uni"]},
            "flashloan_resilience": {"sizing": {"allowed": True}},
        },
    )
    runtime = _runtime(capital_admission_service=CapitalAdmissionService())

    result = svc.prepare_auto_execution(runtime, opp, bn=21, decision=decision)

    assert result.proceed is False
    assert result.blocked_result is not None
    assert result.blocked_result.reason == "capital_admission:flashloan_notional_unavailable"
    assert (
        result.metadata["capitalAdmission"]["stateContract"]["reason_code"]
        == "flashloan_notional_unavailable"
    )
    assert result.metadata["capitalAdmission"]["details"]["notionalTruth"]["complete"] is False


def test_capital_admission_service_denies_stale_profitability_contract_before_family_checks():
    service = CapitalAdmissionService()
    opp = _Opp()
    opp.meta["profitability"] = {
        "stage": "route_mutation_pending_revalidation",
        "source": "route_plan",
        "reason": "mutation_revalidation_required",
        "revalidated": False,
        "stale": True,
        "valid": True,
        "authoritative": False,
        "gross_profit_wei": "20",
        "profit_after_costs_wei": "0",
        "gas_cost_wei": "5",
        "flashloan_fee_wei": "0",
        "amount_in_wei": "100",
        "amount_out_wei": "120",
        "continuity": {"valid": True, "reason": "ok"},
    }
    runtime = _runtime(capital_admission_service=service)

    result = service.evaluate(runtime, opp, decision=SimpleNamespace(metadata={}))

    assert result.allowed is False
    assert result.reason_code == "profitability_contract:mutation_revalidation_required"
    assert result.details["profitability"]["authoritative"] is False


def test_execution_service_prepare_auto_execution_revalidates_profitability_before_capital_admission(
    monkeypatch,
):
    svc = ExecutionService()
    opp = _Opp()
    opp.meta["safety"] = {
        "gas_cost_wei": "5",
        "profit_after_costs_wei": "15",
        "revalidated": True,
        "reason": "ok",
    }
    opp.meta["profitability"] = {
        "stage": "opportunity_revalidated",
        "source": "opportunity_service",
        "reason": "ok",
        "revalidated": True,
        "stale": False,
        "valid": True,
        "authoritative": True,
        "gross_profit_wei": "20",
        "profit_after_costs_wei": "15",
        "gas_cost_wei": "5",
        "flashloan_fee_wei": "0",
        "amount_in_wei": "100",
        "amount_out_wei": "120",
        "continuity": {},
    }
    opp.capital_required_usd = 1_000.0
    decision = SimpleNamespace(
        size_mult=1.0,
        borrow_mult=1.0,
        success_probability=0.95,
        expected_realized_value=25.0,
        metadata={
            "execution_route_plan": {"executable": True, "selected_venues": ["uni"]},
            "flashloan_resilience": {"sizing": {"allowed": True}},
        },
    )

    def _fake_apply_execution_route_plan(*, opp, plan):
        opp2 = SimpleNamespace(**opp.__dict__)
        opp2.route = opp.route
        opp2.id = opp.id
        opp2.route_id = opp.route_id
        opp2.expected_profit_usd = opp.expected_profit_usd
        opp2.capital_required_usd = opp.capital_required_usd
        opp2.meta = dict(opp.meta)
        opp2.meta["execution_route_plan"] = {
            "executable": bool((plan or {}).get("executable", True)),
            "selected_venues": list((plan or {}).get("selected_venues") or ["uni"]),
            "provider_priority": list((plan or {}).get("provider_priority") or []),
            "route_invalid_causes": list((plan or {}).get("route_invalid_causes") or []),
        }
        opp2.meta["profitability_continuity"] = {"valid": True, "reason": "ok"}
        opp2.meta["profitability"] = {
            "stage": "route_mutation_pending_revalidation",
            "source": "route_plan",
            "reason": "mutation_revalidation_required",
            "revalidated": False,
            "stale": True,
            "valid": True,
            "authoritative": False,
            "gross_profit_wei": "20",
            "profit_after_costs_wei": "0",
            "gas_cost_wei": "5",
            "flashloan_fee_wei": "0",
            "amount_in_wei": "100",
            "amount_out_wei": "120",
            "continuity": {"valid": True, "reason": "ok"},
        }
        opp2.min_outs = ["120", "120"]
        return opp2

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.execution_service.apply_execution_route_plan",
        _fake_apply_execution_route_plan,
    )

    runtime = _runtime(capital_admission_service=CapitalAdmissionService())
    result = svc.prepare_auto_execution(runtime, opp, bn=21, decision=decision)

    assert result.proceed is True
    assert result.metadata["profitability"]["stage"] == "post_mutation_submission_gate"
    assert result.metadata["postMutationRevalidation"]["stage"] == "post_mutation_submission_gate"
    assert result.metadata["profitability"]["authoritative"] is True
    assert (
        result.metadata["capitalAdmission"]["details"]["profitability"]["stage"]
        == "post_mutation_submission_gate"
    )
    assert result.opportunity.meta["profitability"]["stage"] == "post_mutation_submission_gate"
    assert (
        result.opportunity.meta["post_mutation_revalidation"]["stage"]
        == "post_mutation_submission_gate"
    )


class _ExplodingTreasuryService:
    def check_family_admission(self, *args, **kwargs):
        raise AssertionError("family admission should not be reached when capital truth is stale")


def test_capital_admission_service_denies_stale_capital_truth_before_family_checks():
    service = CapitalAdmissionService(treasury_service=_ExplodingTreasuryService())
    runtime = _runtime(
        capital_admission_service=service,
        fund_summary={
            "ok": True,
            "health": {
                "capitalTruthStatus": "degraded",
                "capitalTruthReasonCodes": ["capital_truth_freshness_stale"],
                "capitalTruthFreshnessClass": "stale",
                "capitalTruthFreshnessReasonCodes": ["capital_truth_freshness_stale"],
                "suggestedNextAction": "refresh_capital_truth_snapshot",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "capital_truth_freshness_stale",
                "recoveryReasonCodes": ["capital_truth_freshness_stale"],
                "recoveryNextAction": "refresh_capital_truth_snapshot",
            },
        },
    )
    result = service.evaluate(runtime, _Opp(), decision=SimpleNamespace(metadata={}))
    assert result.allowed is False
    assert result.reason_code == "capital_truth_health:capital_truth_freshness_stale"
    assert result.details["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert result.details["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert result.details["familyAdmission"]["reason"] == "pending_family_admission"
