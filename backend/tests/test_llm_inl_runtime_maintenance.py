from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import patch

from victor_ai_bot.llm_inl.config import LLMINLConfig
from victor_ai_bot.llm_inl.runtime import LLMINLRuntime


class _FullQueue:
    def put_nowait(self, item):
        raise asyncio.QueueFull()


def _runtime_stub():
    return SimpleNamespace(
        metrics=SimpleNamespace(
            last_block=123,
            scan_ms=17,
            success_rate_pct=88.0,
            efficiency_pct=72.0,
            basefee_gwei=11.0,
        ),
        cfg=SimpleNamespace(
            execution=SimpleNamespace(
                auto_trading=False,
                send_mode="public",
                gas_mode="standard",
                max_pending_txs=1,
                redact_routes_when_private=False,
            ),
            safety=SimpleNamespace(
                slippage_bps=50,
                minProfitAbs="0",
                minProfitBps=0,
            ),
        ),
        _pending={},
        _mev=None,
        _fioa=None,
    )


def test_store_event_surfaces_websocket_publish_degradation(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False),
        chain="eth",
        data_dir=str(tmp_path),
    )
    runtime._ws_clients.append(_FullQueue())

    item = runtime.store_event("hello operator", kind="event")
    assert item["text"] == "hello operator"

    state = runtime.state()
    assert state["runtime"]["degraded"] is True
    assert state["runtime"]["ws"]["ok"] is False
    assert state["runtime"]["ws"]["last_error_code"] == "ws_publish_failed"


def test_llm_answer_import_failure_is_explicitly_reported(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(
            enabled=True,
            llm_mode="llm",
            llm_provider="openai",
            llm_api_key_env="TEST_LLM_KEY",
            llm_endpoint="https://example.invalid/v1/chat/completions",
        ),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = _runtime_stub()
    orig_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "aiohttp":
            raise ImportError("aiohttp missing")
        return orig_import(name, globals, locals, fromlist, level)

    with patch.dict(os.environ, {"TEST_LLM_KEY": "secret"}, clear=False):
        with patch("builtins.__import__", side_effect=fake_import):
            out = asyncio.run(runtime._llm_answer(rt, agent_id="ops", question="status?"))

    assert out == ""
    state = runtime.state(rt)
    assert state["llm"]["status"]["ok"] is False
    assert state["llm"]["status"]["last_error_code"] == "llm_import_failed"
    assert state["llm"]["last_error"].startswith("llm_import_failed:")


def test_llm_inl_state_additively_exposes_runtime_and_audit_health(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=True),
        chain="eth",
        data_dir=str(tmp_path),
    )
    runtime.store_event("narrative online", kind="status")

    state = runtime.state(_runtime_stub())
    assert state["ok"] is True
    assert "runtime" in state
    assert "audit" in state
    assert state["runtime"]["degraded"] is False
    assert state["audit"]["enabled"] is True



def test_llm_inl_insights_selects_verified_after_cost_profit_over_gross_only(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = _runtime_stub()
    rt._opps = [
        SimpleNamespace(
            id="gross-only",
            route_id="route-gross",
            expected_profit_raw="9000",
            meta={},
        ),
        SimpleNamespace(
            id="net-ok",
            route_id="route-net",
            expected_profit_raw="100",
            meta={"safety": {"profit_after_costs_wei": "250"}},
        ),
    ]

    out = asyncio.run(runtime.insights(rt))

    assert out["top_opportunity_profit_after_costs_wei"] == "250"
    assert out["top_opportunity_profit_after_costs_verified"] is True
    assert out["top_opportunity_profit_after_costs_reason"] == "ok"
    assert any("after costs" in s for s in out["suggestions"])


def test_llm_inl_insights_prefers_route_ready_verified_profit_over_higher_invalid_route_profit(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = _runtime_stub()
    rt._opps = [
        SimpleNamespace(
            id="route-invalid",
            route_id="route-bad",
            expected_profit_raw="9000",
            meta={
                "execution_route_plan": {
                    "executable": False,
                    "route_invalid_causes": ["route_plan_not_executable"],
                },
                "route_invalid_causes": ["route_plan_not_executable"],
                "safety": {"profit_after_costs_wei": "900"},
            },
        ),
        SimpleNamespace(
            id="route-ready",
            route_id="route-good",
            expected_profit_raw="100",
            meta={"safety": {"profit_after_costs_wei": "250"}},
        ),
    ]

    out = asyncio.run(runtime.insights(rt))

    assert out["top_opportunity_profit_after_costs_wei"] == "250"
    assert out["top_opportunity_profit_after_costs_verified"] is True
    assert out["top_opportunity_profit_after_costs_reason"] == "ok"


def test_llm_inl_block_summary_does_not_fall_back_to_gross_profit_when_after_costs_missing(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False, emit_block_summaries=True, block_summary_interval_blocks=1),
        chain="eth",
        data_dir=str(tmp_path),
    )
    runtime.explanation_level = "ADVANCED"
    captured = {}

    def _capture(text: str, *, kind: str = "event", level: str = "info", **meta):
        captured["text"] = text
        captured["kind"] = kind
        captured["level"] = level
        captured["meta"] = meta
        return {"text": text, "kind": kind, "level": level, **meta}

    runtime.store_event = _capture  # type: ignore[assignment]

    rt = _runtime_stub()
    rt._opps = [
        SimpleNamespace(
            id="gross-only",
            route_id="route-gross",
            expected_profit_raw="9000",
            meta={},
        ),
        SimpleNamespace(
            id="net-ok",
            route_id="route-net",
            expected_profit_raw="100",
            meta={"safety": {"profit_after_costs_wei": "250"}},
        ),
    ]

    asyncio.run(runtime._maybe_emit_block_summary(rt))

    assert "top expected after-cost profit" in captured["text"]
    assert '"top_route_id": "route-net"' in captured["text"]
    assert '"top_profit_after_costs_wei": "250"' in captured["text"]
    assert '"top_profit_after_costs_verified": true' in captured["text"]


def test_llm_inl_block_summary_prefers_verified_non_positive_candidate_over_positional_unverified_fallback(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False, emit_block_summaries=True, block_summary_interval_blocks=1),
        chain="eth",
        data_dir=str(tmp_path),
    )
    runtime.explanation_level = "ADVANCED"
    captured = {}

    def _capture(text: str, *, kind: str = "event", level: str = "info", **meta):
        captured["text"] = text
        captured["kind"] = kind
        captured["level"] = level
        captured["meta"] = meta
        return {"text": text, "kind": kind, "level": level, **meta}

    runtime.store_event = _capture  # type: ignore[assignment]

    rt = _runtime_stub()
    rt._opps = [
        SimpleNamespace(
            id="gross-only",
            route_id="route-gross",
            expected_profit_raw="9000",
            meta={},
        ),
        SimpleNamespace(
            id="net-zero",
            route_id="route-zero",
            expected_profit_raw="100",
            meta={"safety": {"profit_after_costs_wei": "0"}},
        ),
    ]

    asyncio.run(runtime._maybe_emit_block_summary(rt))

    assert '"top_route_id": "route-zero"' in captured["text"]
    assert '"top_profit_after_costs_wei": "0"' in captured["text"]
    assert '"top_profit_after_costs_verified": true' in captured["text"]



def test_llm_inl_insights_does_not_treat_profit_after_costs_mismatch_as_verified(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = _runtime_stub()
    rt._opps = [
        SimpleNamespace(
            id="mismatch",
            route_id="route-mismatch",
            expected_profit_raw="9000",
            meta={"profit_after_costs": "900", "safety": {"profit_after_costs_wei": "50"}},
        ),
        SimpleNamespace(
            id="net-ok",
            route_id="route-net",
            expected_profit_raw="100",
            meta={"safety": {"profit_after_costs_wei": "250"}},
        ),
    ]

    out = asyncio.run(runtime.insights(rt))

    assert out["top_opportunity_profit_after_costs_wei"] == "250"
    assert out["top_opportunity_profit_after_costs_verified"] is True
    assert out["top_opportunity_profit_after_costs_reason"] == "ok"


def test_llm_inl_scenario_simulation_skips_route_invalid_leader_and_uses_verified_candidate(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = _runtime_stub()
    rt.rpc_manager = SimpleNamespace(best_read=lambda: "")
    rt.cache = None
    rt._opps = [
        SimpleNamespace(
            id="route-invalid",
            route_id="route-bad",
            can_execute=True,
            route=SimpleNamespace(legs=[SimpleNamespace(amount_in=0)]),
            meta={
                "execution_route_plan": {"executable": False, "route_invalid_causes": ["route_plan_not_executable"]},
                "route_invalid_causes": ["route_plan_not_executable"],
                "safety": {"profit_after_costs_wei": "999"},
            },
        ),
        SimpleNamespace(
            id="route-ready",
            route_id="route-good",
            can_execute=True,
            route=SimpleNamespace(legs=[SimpleNamespace(amount_in=1000)]),
            meta={"safety": {"profit_after_costs_wei": "250"}},
        ),
    ]

    out = asyncio.run(runtime._scenario_simulation(rt))

    assert out["response"] == "No RPC endpoint available for simulation."


def test_llm_inl_rationale_reports_unverified_profit_and_route_not_ready_without_overclaiming(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = _runtime_stub()
    rt.cfg.execution.send_mode = "public"
    opp = SimpleNamespace(
        meta={
            "profit_after_costs": "900",
            "safety": {"profit_after_costs_wei": "50"},
            "execution_route_plan": {
                "executable": False,
                "route_invalid_causes": ["route_plan_not_executable"],
            },
            "route_invalid_causes": ["route_plan_not_executable"],
        }
    )
    res = SimpleNamespace(dry_run=False, ok=False)

    rationale = runtime._rationale_from_state(rt, opp, res)

    assert "profit-after-costs positive" not in rationale
    assert "after-fee truth unavailable" in rationale
    assert "route not ready" in rationale
    assert "route_plan_not_executable" in rationale


def test_on_exec_result_zeroes_pnl_expectation_when_plan_after_costs_truth_mismatches(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = _runtime_stub()
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return kwargs

    runtime.generate_decision_narrative = _capture  # type: ignore[assignment]

    opp = SimpleNamespace(route_id="route-a", meta={"safety": {"profit_after_costs_wei": "250"}})
    res = SimpleNamespace(
        ok=True,
        dry_run=True,
        attempted=True,
        submitted=False,
        reason="",
        tx_hash="",
        plan={"profit_after_costs": "900", "profit_after_costs_wei": "50"},
    )

    runtime.on_exec_result(rt, res=res, opp=opp, mode="auto", agent_id="ops", risk_score=0.1)

    assert captured["pnl_expectation_wei"] == 0
    assert captured["pnl_expectation_verified"] is False
    assert captured["pnl_expectation_reason"] == "profit_after_costs_mismatch"


def test_on_exec_result_uses_verified_meta_only_plan_after_costs_for_pnl_expectation(tmp_path):
    runtime = LLMINLRuntime(
        cfg=LLMINLConfig(enabled=True, persist_history=False),
        chain="eth",
        data_dir=str(tmp_path),
    )
    rt = _runtime_stub()
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return kwargs

    runtime.generate_decision_narrative = _capture  # type: ignore[assignment]

    opp = SimpleNamespace(route_id="route-a", meta={"safety": {"profit_after_costs_wei": "250"}})
    res = SimpleNamespace(
        ok=True,
        dry_run=True,
        attempted=True,
        submitted=False,
        reason="",
        tx_hash="",
        plan={"profit_after_costs": "333"},
    )

    runtime.on_exec_result(rt, res=res, opp=opp, mode="auto", agent_id="ops", risk_score=0.1)

    assert captured["pnl_expectation_wei"] == 333
    assert captured["pnl_expectation_verified"] is True
    assert captured["pnl_expectation_reason"] == "ok"
