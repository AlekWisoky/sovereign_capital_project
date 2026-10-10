from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.runtime_primary_scan_facade import RuntimePrimaryScanFacade


def test_provider_comparison_disables_adaptive_size_ladder():
    runtime = RuntimePrimaryScanFacade()
    runtime.cfg = SimpleNamespace(
        safety=SimpleNamespace(max_borrow_amount=0),
        flags=SimpleNamespace(),
    )
    runtime._rpc_provider_comparison = True

    amounts = runtime._adaptive_scan_amounts(1_000)

    assert amounts == [1_000]


def test_selected_provider_can_run_full_adaptive_size_ladder_after_comparison():
    runtime = RuntimePrimaryScanFacade()
    runtime.cfg = SimpleNamespace(
        safety=SimpleNamespace(max_borrow_amount=100_000),
        flags=SimpleNamespace(),
    )
    runtime._rpc_provider_comparison = False

    amounts = runtime._adaptive_scan_amounts(1_000)

    assert amounts[0] == 1_000
    assert len(amounts) > 1
    assert max(amounts) <= 100_000


import pytest


@pytest.mark.asyncio
async def test_provider_comparison_does_not_force_adaptive_scan(monkeypatch):
    runtime = RuntimePrimaryScanFacade()
    monkeypatch.setattr(runtime, "_build_provider_comparison_pool_event_cache", lambda *args, **kwargs: object())
    calls = []
    probe_calls = []

    class FakeManager:
        def read_candidates(self):
            return ["https://provider.example"]

        def observe_quote_telemetry(self, *args, **kwargs):
            return None

        def snapshot(self):
            return {"read": [{"url": "https://provider.example", "ok": True, "score": 1.0}]}

    class FakeRpc:
        url = "https://provider.example"

    async def fake_discovery(*args, **kwargs):
        return {"v3_pairs": [], "curve_pools": [], "balancer_pools": [], "runtime": {}}

    async def fake_token_amounts(*args, **kwargs):
        return {}, {}

    async def fake_probe(*args, **kwargs):
        probe_calls.append(True)
        return [], {
            "adaptive_size_discovery": {
                "amounts_scanned": ["1000", "500", "1500"],
                "probe_triggered": True,
            }
        }

    async def fake_scan(*args, **kwargs):
        calls.append(bool(kwargs.get("force_adaptive_size_scan")))
        telemetry = kwargs["telemetry_sink"]
        telemetry.update({
            "quotes": {"requests": 1, "quote_successes": 1, "failure_reasons": {}},
            "scan_error": "",
            "adaptive_size_discovery": {"amounts_scanned": ["1000"]},
            "scan_sizing": {"amounts_by_token": {}},
            "route_universe": {},
        })
        return []

    runtime.rpc_manager = FakeManager()
    runtime._build_discovery_context = fake_discovery
    runtime._build_token_scan_amounts = fake_token_amounts
    runtime._scan_primary_opportunities = fake_scan
    runtime._run_bounded_selected_provider_size_probe = fake_probe
    runtime.cache = object()

    result = await runtime._select_rpc_and_scan(
        bootstrap_rpc=FakeRpc(),
        current_block=123,
        amount_in=1_000,
    )

    # Provider comparison and the base-only full-graph pass stay non-adaptive;
    # the bounded frontier schedules only one alternate notional per block.
    assert calls == [False, False, False]
    assert probe_calls == [True]
    frontier = result["telemetry"]["selected_provider_adaptive"]["adaptive_size_discovery"]["frontier_seed"]
    assert frontier["schedule_policy"] == "one_notional_per_tick_rotating"
    assert len(frontier["amounts_scanned"]) == 1


def test_selected_provider_force_flag_bypasses_provider_comparison(monkeypatch):
    runtime = RuntimePrimaryScanFacade()
    runtime.cfg = SimpleNamespace(
        safety=SimpleNamespace(max_borrow_amount=100_000),
        flags=SimpleNamespace(),
    )
    runtime._rpc_provider_comparison = True
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0")

    amounts = runtime._adaptive_scan_amounts(
        1_000,
        force_adaptive_size_scan=True,
    )

    assert amounts[0] == 1_000
    assert len(amounts) > 1
    assert max(amounts) <= 100_000
