from types import SimpleNamespace

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


EXTRACTED_METHODS = {
    "_opp_is_exec_ready",
    "_scale_opportunity",
    "_record_tick_failure",
    "_clear_tick_state_after_failure",
    "_contain_tick_failure",
    "_safe_decide_opportunities",
    "_safe_annotate_can_execute",
    "_simple_auto_trade_candidate",
    "_decision_auto_trade_candidate",
    "_maybe_dispatch_auto_trade",
}


class _ExecutionService:
    def __init__(self):
        self.calls = []

    def scale_opportunity(self, opp, mult):
        self.calls.append((opp, mult))
        return {"scaled": opp, "mult": mult}


class _Runtime(RuntimeDecisionFacade):
    def __init__(self):
        self.metrics = SimpleNamespace(last_error="", failed_ticks=0)
        self._errors = []
        self._opps = []
        self._spread_opps = []
        self._spread_last = {}
        self._engine_last = {
            "items": [{"id": "stale"}],
            "capabilities": {"stale": True},
            "summary": {"engines": ["stale"]},
        }


class _AutoTradeRuntime(RuntimeDecisionFacade):
    def __init__(self, *, brain_mode="off", max_pending_txs=1):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(brain_mode=brain_mode, max_pending_txs=max_pending_txs)
        )
        self._pending = {}
        self._opps = []
        self._auto_queue = []
        self._auto_trading = True
        self._exec_task = None
        self._scheduled = []
        self._cb = SimpleNamespace(allow_auto_trading=lambda: True)
        self._capital_engine_state = {
            "capital_engine": {
                "deployable_bankroll_wei": 0,
                "family_allocations_wei": {},
            }
        }

    def capital_engine_state(self):
        return self._capital_engine_state

    async def _execute_auto(self, opp, bn, decision=None):
        self._scheduled.append((opp, bn, decision))


def _opp(
    opp_id: str,
    *,
    can_execute: bool = True,
    exec_ready: bool = True,
    profit_after_costs_wei: str = "5",
    route_plan_executable: bool = True,
    route_invalid_causes: list[str] | None = None,
    route_runtime_degraded: bool = False,
    route_runtime_reason_codes: list[str] | None = None,
    profitability: dict | None = None,
    post_mutation_revalidation: dict | None = None,
):
    meta = {"safety": {"exec_ready": exec_ready, "profit_after_costs_wei": profit_after_costs_wei}}
    if not route_plan_executable or route_invalid_causes:
        meta["execution_route_plan"] = {
            "executable": route_plan_executable,
            "route_invalid_causes": list(route_invalid_causes or []),
        }
    if route_runtime_degraded or route_runtime_reason_codes:
        meta["execution_route_runtime"] = {
            "degraded": bool(route_runtime_degraded),
            "reason_codes": list(route_runtime_reason_codes or []),
        }
    if profitability is not None:
        meta["profitability"] = dict(profitability)
    if post_mutation_revalidation is not None:
        meta["post_mutation_revalidation"] = dict(post_mutation_revalidation)
    return SimpleNamespace(
        id=opp_id,
        can_execute=can_execute,
        meta=meta,
    )


def test_opp_is_exec_ready_requires_flags_and_route_truth():
    runtime = _AutoTradeRuntime()

    assert runtime._opp_is_exec_ready(_opp("opp-1")) is True
    assert runtime._opp_is_exec_ready(_opp("opp-2", can_execute=False)) is False
    assert runtime._opp_is_exec_ready(_opp("opp-3", exec_ready=False)) is False
    assert (
        runtime._opp_is_exec_ready(
            _opp(
                "opp-4",
                route_plan_executable=False,
                route_invalid_causes=["route_plan_not_executable"],
            )
        )
        is False
    )
    assert (
        runtime._opp_is_exec_ready(
            _opp(
                "opp-5",
                route_runtime_degraded=True,
                route_runtime_reason_codes=["capture_runtime_degraded"],
            )
        )
        is False
    )


def test_opp_is_exec_ready_requires_verified_positive_profitability_truth():
    runtime = _AutoTradeRuntime()

    stale = _opp(
        "opp-stale",
        profitability={
            "stage": "post_scan",
            "source": "scan",
            "reason": "profitability_metadata_stale",
            "revalidated": False,
            "stale": True,
            "valid": False,
            "authoritative": False,
            "profit_after_costs_wei": "25",
        },
        post_mutation_revalidation={
            "reason_code": "route_mutated",
            "profitability": {
                "stage": "post_mutation_submission_gate",
                "source": "execution",
                "reason": "route_mutated",
                "revalidated": False,
                "stale": True,
                "valid": False,
                "authoritative": False,
                "profit_after_costs_wei": "25",
            },
        },
    )

    assert runtime._opp_is_exec_ready(stale) is False


def test_simple_auto_trade_candidate_respects_pending_cap_and_exec_ready():
    runtime = _AutoTradeRuntime(max_pending_txs=1)
    runtime._opps = [_opp("not-ready", exec_ready=False), _opp("chosen")]

    assert runtime._simple_auto_trade_candidate().id == "chosen"

    runtime._pending = {"0x1": {}}
    assert runtime._simple_auto_trade_candidate() is None


def test_simple_auto_trade_candidate_prefers_highest_verified_after_fee_profitability():
    runtime = _AutoTradeRuntime(max_pending_txs=2)
    runtime._opps = [
        _opp("lower", profit_after_costs_wei="5"),
        _opp("higher", profit_after_costs_wei="25"),
        _opp(
            "stale-contract",
            profitability={
                "stage": "post_scan",
                "source": "scan",
                "reason": "profitability_metadata_stale",
                "revalidated": False,
                "stale": True,
                "valid": False,
                "authoritative": False,
                "profit_after_costs_wei": "50",
            },
        ),
    ]

    assert runtime._simple_auto_trade_candidate().id == "higher"


def test_decision_auto_trade_candidate_prefers_route_ready_portfolio_head_and_requires_ready_fallback():
    runtime = _AutoTradeRuntime(brain_mode="auto")
    runtime._opps = [
        _opp("fallback"),
        _opp(
            "portfolio-1",
            route_plan_executable=False,
            route_invalid_causes=["route_plan_not_executable"],
        ),
        _opp("portfolio-2"),
    ]
    runtime._auto_queue = ["portfolio-1", "portfolio-2"]

    chosen = runtime._decision_auto_trade_candidate(
        SimpleNamespace(action="trade", portfolio=["portfolio-1", "portfolio-2"], opp_id="fallback")
    )
    assert chosen.id == "portfolio-2"

    runtime._opps = [_opp("fallback", exec_ready=False), _opp("opp-id-only", exec_ready=False)]
    chosen = runtime._decision_auto_trade_candidate(
        SimpleNamespace(action="trade", portfolio=["missing"], opp_id="opp-id-only")
    )
    assert chosen is None


@__import__("pytest").mark.asyncio
async def test_maybe_dispatch_auto_trade_schedules_simple_mode_candidate():
    runtime = _AutoTradeRuntime(brain_mode="off")
    runtime._opps = [_opp("chosen")]

    dispatched = runtime._maybe_dispatch_auto_trade(current_block=123)

    assert dispatched is True
    assert runtime._exec_task is not None
    await runtime._exec_task
    assert runtime._scheduled == [(runtime._opps[0], 123, None)]


@__import__("pytest").mark.asyncio
async def test_maybe_dispatch_auto_trade_schedules_decision_selected_candidate():
    runtime = _AutoTradeRuntime(brain_mode="auto")
    runtime._opps = [_opp("opp-1"), _opp("opp-2")]

    decision = SimpleNamespace(action="trade", portfolio=["opp-2"], opp_id="opp-1")
    dispatched = runtime._maybe_dispatch_auto_trade(current_block=456, decision=decision)

    assert dispatched is True
    await runtime._exec_task
    assert runtime._scheduled == [(runtime._opps[1], 456, decision)]


@__import__("pytest").mark.asyncio
async def test_maybe_dispatch_auto_trade_rejects_route_invalid_decision_fallback():
    runtime = _AutoTradeRuntime(brain_mode="auto")
    runtime._opps = [
        _opp(
            "opp-1", route_plan_executable=False, route_invalid_causes=["route_plan_not_executable"]
        ),
    ]

    decision = SimpleNamespace(action="trade", portfolio=["missing"], opp_id="opp-1")
    dispatched = runtime._maybe_dispatch_auto_trade(current_block=789, decision=decision)

    assert dispatched is False
    assert runtime._exec_task is None
    assert runtime._scheduled == []


def test_runtime_bundle_inherits_decision_facade():
    assert issubclass(RuntimeBundle, RuntimeDecisionFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_scale_opportunity_delegates_to_execution_service():
    runtime = _Runtime()
    runtime._execution_service = _ExecutionService()

    result = runtime._scale_opportunity({"id": "opp-1"}, 0.5)

    assert result == {"scaled": {"id": "opp-1"}, "mult": 0.5}
    assert runtime._execution_service.calls == [({"id": "opp-1"}, 0.5)]


def test_scale_opportunity_returns_original_without_execution_service():
    runtime = _Runtime()
    runtime._execution_service = None
    opp = {"id": "opp-1"}

    assert runtime._scale_opportunity(opp, 0.5) is opp


def test_empty_engine_snapshot_returns_new_default_mapping():
    runtime = _Runtime()

    first = runtime._empty_engine_snapshot()
    second = runtime._empty_engine_snapshot()

    assert first == {"items": [], "capabilities": {}, "summary": {"engines": []}}
    assert second == first
    assert second is not first


def test_contain_tick_failure_clears_runtime_state_and_records_error():
    import asyncio

    runtime = _Runtime()
    runtime._state_lock = asyncio.Lock()
    runtime._opps = [{"id": "stale"}]
    runtime._spread_opps = [{"id": "spread"}]
    runtime._spread_last = {"count": 1}

    asyncio.run(runtime._contain_tick_failure(RuntimeError("tick boom")))

    assert runtime.metrics.last_error == "tick boom"
    assert runtime.metrics.failed_ticks == 1
    assert runtime._errors == ["tick boom"]
    assert runtime._opps == []
    assert runtime._spread_opps == []
    assert runtime._spread_last == {}
    assert runtime._engine_last == {"items": [], "capabilities": {}, "summary": {"engines": []}}


def test_safe_decide_opportunities_forwards_capital_budgets_from_capital_engine_state():
    runtime = _AutoTradeRuntime(brain_mode="auto")
    runtime._capital_engine_state = {
        "capital_engine": {
            "deployable_bankroll_wei": 321,
            "family_allocations_wei": {"flashloan_atomic": 123},
        }
    }

    captured = {}

    class _Decision:
        def annotate_and_decide(self, opps, **kwargs):
            captured.update(kwargs)
            return "ok"

    runtime._decision = _Decision()

    out = runtime._safe_decide_opportunities(
        [_opp("opp-1")],
        current_block=10,
        pending_txs=0,
        auto_enabled=True,
        gas_budget_remaining_wei=77,
    )

    assert out == "ok"
    assert captured["gas_budget_remaining_wei"] == 77
    assert captured["capital_budget_remaining_wei"] == 321
    assert captured["family_capital_remaining_wei"] == {"flashloan_atomic": 123}


def test_safe_decide_opportunities_coerces_stringified_capital_truth_without_dropping_budgets():
    runtime = _AutoTradeRuntime(brain_mode="auto")
    runtime._capital_engine_state = {
        "capital_engine": {
            "deployable_bankroll_wei": "1e3",
            "family_allocations_wei": {
                "flashloan_atomic": "9e2",
                "funding_arb": "bad",
            },
        }
    }

    captured = {}

    class _Decision:
        def annotate_and_decide(self, opps, **kwargs):
            captured.update(kwargs)
            return "ok"

    runtime._decision = _Decision()

    out = runtime._safe_decide_opportunities(
        [_opp("opp-1")],
        current_block=10,
        pending_txs=0,
        auto_enabled=True,
        gas_budget_remaining_wei=77,
    )

    assert out == "ok"
    assert captured["capital_budget_remaining_wei"] == 1000
    assert captured["family_capital_remaining_wei"] == {"flashloan_atomic": 900}
