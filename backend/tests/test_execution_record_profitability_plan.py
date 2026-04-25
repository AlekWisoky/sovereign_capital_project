from collections import deque
from queue import Queue
from types import SimpleNamespace

import pytest

from victor_ai_bot.execution import ExecResult
from victor_ai_bot.runtime_services.execution_service import ExecutionService


@pytest.mark.asyncio
async def test_pnl_trade_row_prefers_canonical_plan_profitability_over_stale_safety():
    svc = ExecutionService()
    pnl_rows = []

    class _PNL:
        async def add_trade(self, row):
            pnl_rows.append(dict(row))
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
            "safety": {
                "profit_after_costs_wei": "999",
                "gas_cost_wei": "111",
                "flashloan_fee_wei": "22",
            },
            "brain": {},
            "route_family": "flashloan_atomic",
            "strategy_family": "flashloan_atomic",
            "pending_context": {"summary": {"count": 2}},
        },
        route=SimpleNamespace(legs=[SimpleNamespace(venue="uni", dex="uni", to="0xabc")]),
    )
    result = ExecResult(
        True,
        False,
        "sent",
        tx_hash="0xabc",
        plan={
            "profit_after_costs": "17",
            "gas_cost": "9",
            "flashloan_fee": "4",
            "gas_limit": 210000,
            "max_fee": "12",
            "priority_fee": "2",
            "amount_in": "100",
            "route_id": "route-1",
            "current_block": 101,
            "send_mode": "private",
            "profitability": {
                "gross_profit_wei": "30",
                "profit_after_costs_wei": "17",
                "gas_cost_wei": "9",
                "flashloan_fee_wei": "4",
            },
        },
        attempted=True,
        submitted=True,
    )

    await svc.record_execution(runtime, result, opp, latency_ms=44, mode="auto")

    assert pnl_rows[0]["expected_profit_after_costs_wei"] == "17"
    assert pnl_rows[0]["estimated_gas_cost_wei"] == "9"
    assert pnl_rows[0]["flashloan_fee_wei"] == "4"
