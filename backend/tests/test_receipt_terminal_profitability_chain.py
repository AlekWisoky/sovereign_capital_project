from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.execution import ExecResult

from tests.test_flashloan_borrowing_lifecycle_proof import _FlashloanSettlementRuntime


class _Audit:
    def __init__(self):
        self.items = []

    def append(self, event, payload, **kwargs):
        self.items.append({"event": event, "payload": dict(payload or {}), **kwargs})
        return self.items[-1]


def _authority() -> dict:
    return {
        "source": "execution_plan",
        "stage": "execution_preflight_gate",
        "reason": "ok",
        "authoritative": True,
        "live_gas_derived": True,
        "profitability": {
            "stage": "execution_preflight_gate",
            "source": "execution",
            "reason": "ok",
            "revalidated": True,
            "stale": False,
            "valid": True,
            "authoritative": True,
            "gross_profit_wei": "30",
            "profit_after_costs_wei": "17",
            "profit_after_costs_usd_micro": 17000000,
            "gas_cost_wei": "9",
            "flashloan_fee_wei": "4",
            "amount_in_wei": "100",
            "amount_out_wei": "130",
            "continuity": {},
        },
    }


def _post_mutation_contract() -> dict:
    return {
        "source": "execution_service",
        "stage": "post_mutation_submission_gate",
        "reason_code": "ok",
        "degraded": False,
        "authoritative": True,
        "revalidated": True,
        "valid": True,
        "continuity": {},
        "safety": {
            "revalidated": True,
            "reason": "ok",
            "gas_cost_wei": "9",
            "profit_after_costs_wei": "17",
            "flashloan_fee_wei": "4",
        },
        "routeInvalidCauses": [],
        "selectedVenues": ["uni", "curve"],
        "providerPriority": ["aave"],
        "profitability": dict(_authority()["profitability"]),
    }


def test_execution_live_state_exposes_terminal_profitability_authority():
    runtime = SimpleNamespace(
        _pending={
            "0xflash": {
                "route_family": "flashloan_atomic",
                "strategy_family": "flashloan_atomic",
                "terminal_profitability_authority": _authority(),
                "post_mutation_revalidation": _post_mutation_contract(),
                "capital_admission": {"allowed": True, "reason_code": "ok", "details": {}},
                "capture_meta": {
                    "lane": "PRIVATE",
                    "endpoint_hint": "rpc-fast",
                    "metadata": {
                        "endpoint_selection": {"endpoint": "rpc-fast"},
                        "execution_route_plan": {"executable": True},
                        "flashloan_resilience": {"selected_provider": "aave", "sizing": {}},
                    },
                },
                "created_at_ms": 123,
            }
        }
    )
    live = ExecutionService().build_live_state(runtime)
    item = live["items"][0]
    assert item["terminalProfitabilityAuthority"]["live_gas_derived"] is True
    assert item["capitalAdmission"]["allowed"] is True
    assert item["capitalAdmission"]["stateContract"]["reason_code"] == "ok"
    assert item["postMutationRevalidation"]["stage"] == "post_mutation_submission_gate"


def test_execution_summary_exposes_last_terminal_profitability_authority():
    runtime = SimpleNamespace(
        _pending={
            "0xflash": {
                "route_family": "flashloan_atomic",
                "strategy_family": "flashloan_atomic",
                "terminal_profitability_authority": _authority(),
                "post_mutation_revalidation": _post_mutation_contract(),
                "capital_admission": {"allowed": True, "reason_code": "ok", "details": {}},
                "capture_meta": {
                    "lane": "PRIVATE",
                    "endpoint_hint": "rpc-fast",
                    "metadata": {
                        "endpoint_selection": {"endpoint": "rpc-fast"},
                        "execution_route_plan": {"executable": True},
                        "flashloan_resilience": {"selected_provider": "aave", "sizing": {}},
                    },
                },
                "created_at_ms": 123,
            }
        }
    )
    summary = ExecutionService().summarize(runtime)
    assert summary["lastTerminalProfitabilityAuthority"]["stage"] == "execution_preflight_gate"
    assert summary["lastPostMutationRevalidation"]["stage"] == "post_mutation_submission_gate"
    assert summary["lastCapitalAdmission"]["stateContract"]["reason_code"] == "ok"


def test_settlement_sync_exposes_terminal_profitability_chain(tmp_path: Path):
    runtime = _FlashloanSettlementRuntime(tmp_path)
    runtime._bankroll.record_trade(
        success=True, realized_profit_after_gas_wei=6_000_000, amount_in_wei=1_500_000
    )
    pending = {
        "strategy_family": "flashloan_atomic",
        "route_family": "flashloan_atomic",
        "flashloan_fee_wei": "4500",
        "borrow_cost_usd": 1.25,
        "terminal_profitability_authority": _authority(),
        "capital_admission": {
            "allowed": True,
            "reason_code": "ok",
            "details": {"terminalProfitabilityAuthority": _authority()},
            "stateContract": {
                "phase": "capital_admission",
                "status": "ok",
                "reason_code": "ok",
                "degraded": False,
                "blocked": False,
                "denied": False,
                "sticky_cycle": True,
                "details": {},
            },
        },
        "capture_meta": {
            "lane": "PRIVATE",
            "metadata": {
                "flashloan_resilience": {
                    "selected_provider": "aave",
                    "sizing": {"borrowCostUsd": 1.25},
                }
            },
        },
    }

    out = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xsettle",
        pending=pending,
        decoded={
            "realized_profit_after_gas_wei": "6000000",
            "realized_profit_after_gas_usd_micro": "6000000",
            "realized_gas_cost_wei": "200000",
            "realized_gas_cost_usd_micro": "1000000",
        },
        status=1,
        amount_in=1_500_000,
        expected_after=7_000_000,
        realized_after=6_000_000,
        submit_to_receipt_ms=420,
        route_id="route-1",
        route_family="flashloan_atomic",
        strategy_family="flashloan_atomic",
        capture_lane_pending="PRIVATE",
    )

    assert out["terminalProfitabilityAuthority"]["live_gas_derived"] is True
    assert out["terminalProfitability"]["profit_after_costs_wei"] == "17"
    assert out["capitalAdmission"]["allowed"] is True
    assert out["capitalAdmission"]["stateContract"]["reason_code"] == "ok"
    assert out["profitabilityChain"]["realizedAfterGasWei"] == "6000000"
    assert out["profitabilityChain"]["expectedAfterCostsWei"] == "17"
    assert (
        runtime._last_settlement_sync["terminalProfitabilityAuthority"]["stage"]
        == "execution_preflight_gate"
    )
    assert (
        runtime._treasury.cfg.meta["last_settlement_terminal_profitability_authoritative"] is True
    )


def test_receipt_summary_exposes_last_terminal_profitability_authority():
    runtime = SimpleNamespace(
        _last_settlement_sync={
            "terminalProfitabilityAuthority": _authority(),
            "capitalAdmission": {"allowed": True},
        },
        execution_live_state=lambda: {"items": []},
    )
    summary = ReceiptService().summarize(runtime)
    assert summary["lastTerminalProfitabilityAuthority"]["stage"] == "execution_preflight_gate"
    assert summary["lastCapitalAdmission"]["allowed"] is True
    assert summary["lastCapitalAdmission"]["stateContract"]["reason_code"] == "ok"


def test_audit_reward_trace_persists_terminal_profitability_authority():
    audit = _Audit()
    runtime = SimpleNamespace(
        _cc=SimpleNamespace(audit=audit, controls=SimpleNamespace(reward_trace_enabled=True))
    )
    ReceiptService().audit_reward_trace(
        runtime,
        tx_hash="0xabc",
        mode="auto",
        route_id="route-1",
        status=1,
        submit_to_receipt_ms=420,
        realized_after=6_000_000,
        expected_after=7_000_000,
        reward_trace={"score": 1.0},
        pending={
            "terminal_profitability_authority": _authority(),
            "capital_admission": {"allowed": True, "reason_code": "ok"},
        },
    )

    payload = audit.items[0]["payload"]
    assert payload["terminal_profitability_authority"]["live_gas_derived"] is True
    assert payload["terminal_profitability"]["profit_after_costs_wei"] == "17"
    assert payload["capital_admission"]["allowed"] is True
    assert (
        payload["profitability_chain"]["terminalProfitabilityAuthority"]["stage"]
        == "execution_preflight_gate"
    )


def test_pending_submission_prefers_terminal_profitability_authority_expected_after():
    svc = ExecutionService()
    opp = SimpleNamespace(
        route_id="route-1",
        expected_profit_raw="99",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="100")]),
        meta={
            "route_family": "flashloan_atomic",
            "strategy_family": "flashloan_atomic",
            "capture": {"metadata": {"endpoint_selection": {}, "envelope": {}}},
        },
    )
    result = ExecResult(
        ok=True,
        dry_run=False,
        reason="submitted",
        tx_hash="0xabc",
        plan={
            "terminalProfitabilityAuthority": _authority(),
            "postMutationRevalidation": _post_mutation_contract(),
            "capitalAdmission": {"allowed": True},
            "profit_after_costs": "7000000",
        },
    )
    pending = svc._build_pending_submission(
        SimpleNamespace(), result, opp, latency_ms=12, mode="auto"
    )
    assert pending["expected_after"] == "17"
