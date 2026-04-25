from collections import deque
from queue import Queue
from types import SimpleNamespace

import pytest

from victor_ai_bot.execution import ExecResult
from victor_ai_bot.runtime_services.execution_service import ExecutionService


def _profitability(stage: str = "execution_preflight"):
    return {
        "stage": stage,
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
    }


def test_sync_terminal_profitability_authority_threads_plan_back_into_capital_admission():
    svc = ExecutionService()
    opp = SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        meta={
            "capital_admission": {
                "allowed": True,
                "reason_code": "ok",
                "details": {"capitalSource": "flashloan"},
            }
        },
    )
    result = ExecResult(
        True,
        False,
        "sent",
        tx_hash="0xabc",
        plan={"profitability": _profitability()},
        attempted=True,
        submitted=True,
    )

    svc._sync_terminal_profitability_authority(opp, result)

    assert opp.meta["profitability"]["stage"] == "execution_preflight"
    assert opp.meta["terminal_profitability_authority"]["live_gas_derived"] is True
    assert (
        opp.meta["capital_admission"]["details"]["terminalProfitability"]["profit_after_costs_wei"]
        == "17"
    )
    assert (
        opp.meta["capital_admission"]["details"]["terminalProfitabilityAuthority"]["profitability"][
            "gas_cost_wei"
        ]
        == "9"
    )
    assert (
        result.plan["capitalAdmission"]["details"]["terminalProfitabilityAuthority"]["stage"]
        == "execution_preflight"
    )
    assert (
        result.plan["terminalProfitabilityAuthority"]["profitability"]["profit_after_costs_wei"]
        == "17"
    )


def test_build_pending_submission_preserves_terminal_authority_and_capital_admission():
    svc = ExecutionService()
    runtime = SimpleNamespace()
    opp = SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        meta={
            "brain": {},
            "pending_context": {"summary": {"count": 2}},
            "route_family": "flashloan_atomic",
            "strategy_family": "flashloan_atomic",
            "capital_admission": {"allowed": True, "reason_code": "ok", "details": {}},
        },
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(
                    venue="uni", dex="uni", token_in="USDC", token_out="WETH", to="0xabc"
                )
            ]
        ),
    )
    result = ExecResult(
        True,
        False,
        "sent",
        tx_hash="0xabc",
        plan={
            "route_id": "route-1",
            "amount_in": "100",
            "profit_after_costs": "17",
            "gas_cost": "9",
            "profitability": _profitability(),
        },
        attempted=True,
        submitted=True,
    )

    svc._sync_terminal_profitability_authority(opp, result)
    pending = svc._build_pending_submission(runtime, result, opp, latency_ms=44, mode="auto")

    assert pending["terminal_profitability_authority"]["stage"] == "execution_preflight"
    assert pending["terminal_profitability_authority"]["live_gas_derived"] is True
    assert (
        pending["capital_admission"]["details"]["terminalProfitabilityAuthority"]["profitability"][
            "profit_after_costs_wei"
        ]
        == "17"
    )


@pytest.mark.asyncio
async def test_record_execution_log_plan_keeps_terminal_authority_and_capital_admission():
    svc = ExecutionService()

    class _PNL:
        async def add_trade(self, row):
            return 1

    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        metrics=SimpleNamespace(attempted=0),
        _exec_log=deque(maxlen=20),
        _pnl=_PNL(),
        _pending={},
        _pending_gas_est_wei=0,
        _receipt_q=Queue(),
        _errors=deque(maxlen=20),
        _create_replay_bundle=lambda **kwargs: "bundle-1",
    )
    opp = SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        expected_profit_raw="250",
        strategy="flashloan_atomic",
        meta={
            "brain": {},
            "route_family": "flashloan_atomic",
            "strategy_family": "flashloan_atomic",
            "pending_context": {},
            "capital_admission": {"allowed": True, "reason_code": "ok", "details": {}},
        },
        route=SimpleNamespace(legs=[SimpleNamespace(venue="uni", dex="uni", to="0xabc")]),
    )
    result = ExecResult(
        True,
        False,
        "sent",
        tx_hash="0xabc",
        plan={"profitability": _profitability()},
        attempted=True,
        submitted=True,
    )

    svc._sync_terminal_profitability_authority(opp, result)
    await svc.record_execution(runtime, result, opp, latency_ms=44, mode="auto")

    plan = runtime._exec_log[-1]["plan"]
    assert plan["terminalProfitabilityAuthority"]["live_gas_derived"] is True
    assert (
        plan["capitalAdmission"]["details"]["terminalProfitabilityAuthority"]["stage"]
        == "execution_preflight"
    )
