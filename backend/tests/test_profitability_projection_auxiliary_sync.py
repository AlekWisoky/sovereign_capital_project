from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.aqe.meta.runtime import MetaStrategyRuntime
from victor_ai_bot.llm_inl.config import LLMINLConfig
from victor_ai_bot.llm_inl.runtime import LLMINLRuntime
from victor_ai_bot.runtime_subsystems.replay_store import ReplayBundleStore
from victor_ai_bot.superstructure.path_planning import StrategyPathPlanner
from victor_ai_bot.superstructure.runtime import SuperstructureRuntime


def _stale_opp() -> SimpleNamespace:
    return SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        strategy="flashloan_atomic",
        expected_profit_raw="250",
        expected_profit_usd="12.5",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(amount_in="100000", dex="uni", to="0xabc"),
                SimpleNamespace(min_out="100250", dex="sushi", to="0xdef"),
            ]
        ),
        meta={
            "profitability_continuity": {
                "valid": False,
                "reason": "mutation_profitability_invalid",
            },
            "safety": {
                "revalidated": False,
                "profit_after_costs_wei": "240",
                "profit_after_costs_usd_micro": 12000000,
            },
            "brain": {"p_success": 0.82, "gas_mode": "standard", "reason": "brain-picked"},
            "unit_econ": {"expected_profit_usd_micro": 12500000, "gas_cost_usd_micro": 250000},
        },
    )


def test_llm_inl_block_summary_zeros_stale_profit(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False, block_summary_interval_blocks=1),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = SimpleNamespace(
        metrics=SimpleNamespace(
            last_block=100,
            scan_ms=17,
            success_rate_pct=88.0,
            efficiency_pct=72.0,
            basefee_gwei=11.0,
        ),
        cfg=SimpleNamespace(execution=SimpleNamespace(gas_mode="standard", send_mode="public")),
        _opps=[_stale_opp()],
    )

    asyncio.run(runtime._maybe_emit_block_summary(rt))

    item = runtime._memory.last()
    assert item is not None
    assert "top expected profit" in item["text"]
    assert "0 wei" in item["text"]


def test_superstructure_runtime_and_path_planner_zero_stale_profit(tmp_path):
    opp = _stale_opp()

    runtime = SuperstructureRuntime(cfg={"enabled": False}, chain="eth", data_dir=str(tmp_path))
    proposal = runtime.build_trade_proposal(opp=opp)
    assert proposal.expected_return == 0.0
    assert proposal.meta["profitability"]["stale"] is True

    planner = StrategyPathPlanner(data_dir=str(tmp_path), chain="eth")
    assert planner._profit(opp) == 0


def test_replay_store_summary_zeroes_stale_profit_and_marks_reason(tmp_path):
    items = ReplayBundleStore(
        data_dir=str(tmp_path), chain="eth", chain_id=1
    ).summarize_opportunities([_stale_opp()])
    assert len(items) == 1
    item = items[0]
    assert item["expected_profit_after_costs_wei"] == "0"
    assert item["expected_profit_after_gas_usd_micro"] == 0
    assert item["expected_profit_usd_micro"] == 0
    assert any(str(x).startswith("profitability:") for x in item["why"])
    assert item["post_mutation_revalidation"] == {}
    assert item["state_contract"]["phase"] == "candidate_trade_reporting"


def test_meta_runtime_telemetry_zeroes_stale_profit(tmp_path):
    meta = MetaStrategyRuntime(
        chain_name="eth",
        data_dir=str(tmp_path),
        cfg=SimpleNamespace(enabled=False, mode="observe", max_registry_items=8),
    )
    rt = SimpleNamespace(
        metrics_state=lambda: {"scan_ms": 25.0},
        _opps=[_stale_opp()],
        _route_fail_rate=lambda: 0.12,
        cfg=SimpleNamespace(
            safety=SimpleNamespace(minProfitAbs="0", minProfitBps=0, slippage_bps=50)
        ),
    )

    telemetry = meta._telemetry_from_runtime(rt)
    assert telemetry["expected_profit_usd"] == 0.0
    assert telemetry["gas_cost_usd"] == 0.25
