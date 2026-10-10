from __future__ import annotations

import asyncio

from types import SimpleNamespace

import pytest

from victor_ai_bot.cache import PerBlockCache
from victor_ai_bot.rpc_manager import RpcManager
from victor_ai_bot.rpc_economic_selector import RpcEconomicEvidence, select_best_rpc_evidence
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import RuntimePrimaryScanFacade


def test_rpc_preferences_extend_live_read_provider_universe():
    manager = RpcManager(
        rpc_read=["https://rpc-config.example"],
        rpc_send=["https://rpc-config.example"],
    )
    manager._read["https://rpc-config.example"].last_seen_block = 100
    urls = manager.sync_read_preferences(["https://premium.example"])
    assert urls == ["https://rpc-config.example", "https://premium.example"]
    assert "https://premium.example" in manager.read_candidates()
    manager.sync_read_preferences([])
    assert "https://premium.example" not in manager.read_candidates()
    assert "https://rpc-config.example" in manager.read_candidates()
    manager.sync_read_preferences(["https://premium.example"])
    manager._read["https://premium.example"].quote_unhealthy_until = 9_999_999_999.0
    assert "https://premium.example" not in manager.read_candidates()


def test_rpc_economic_selector_prefers_higher_after_fee_profit_and_ignores_unhealthy():
    evidence = [
        RpcEconomicEvidence(
            endpoint="https://rpc-a.example",
            provider="rpc-a.example",
            profit_after_costs_usd_micro=120,
            profitable_opportunity_count=1,
            quote_requests=10,
            quote_successes=10,
            operational_score=10.0,
        ),
        RpcEconomicEvidence(
            endpoint="https://rpc-b.example",
            provider="rpc-b.example",
            profit_after_costs_usd_micro=240,
            profitable_opportunity_count=2,
            quote_requests=10,
            quote_successes=10,
            operational_score=20.0,
        ),
        RpcEconomicEvidence(
            endpoint="https://rpc-c.example",
            provider="rpc-c.example",
            profit_after_costs_usd_micro=999,
            profitable_opportunity_count=9,
            quote_requests=10,
            quote_successes=10,
            operational_score=1.0,
            healthy=False,
        ),
    ]
    selected, ordered = select_best_rpc_evidence(evidence)
    assert selected is not None
    assert selected.endpoint == "https://rpc-b.example"
    assert [item.endpoint for item in ordered] == [
        "https://rpc-b.example",
        "https://rpc-a.example",
    ]


def test_rpc_economic_selector_uses_signed_observed_return_when_no_provider_is_profitable():
    evidence = [
        RpcEconomicEvidence(
            endpoint="https://rpc-a.example",
            provider="rpc-a.example",
            profit_after_costs_usd_micro=0,
            profitable_opportunity_count=0,
            quote_requests=20,
            quote_successes=18,
            observed_after_cost_return_bps=-42.0,
            successful_quote_edge_count=12,
            operational_score=5.0,
        ),
        RpcEconomicEvidence(
            endpoint="https://rpc-b.example",
            provider="rpc-b.example",
            profit_after_costs_usd_micro=0,
            profitable_opportunity_count=0,
            quote_requests=20,
            quote_successes=19,
            observed_after_cost_return_bps=-7.5,
            successful_quote_edge_count=10,
            operational_score=1.0,
        ),
    ]
    selected, _ = select_best_rpc_evidence(evidence)
    assert selected is not None
    assert selected.endpoint == "https://rpc-b.example"


@pytest.mark.asyncio
async def test_runtime_rpc_race_selects_higher_economic_provider_without_broadcast(monkeypatch):
    class _Manager:
        def __init__(self):
            self.telemetry = []

        def read_candidates(self):
            return ["https://rpc-a.example", "https://rpc-b.example"]

        def observe_quote_telemetry(self, url, **kwargs):
            self.telemetry.append((url, kwargs))

        async def gas_price_consensus(self):
            return {"gas_price_wei": 100, "status": "consensus", "observations": [], "anomalies": []}

        def snapshot(self):
            return {
                "read": [
                    {"url": "https://rpc-a.example", "ok": True, "score": 10.0},
                    {"url": "https://rpc-b.example", "ok": True, "score": 20.0},
                ]
            }

    class _Rpc:
        def __init__(self, url):
            self.url = url

    class _Client:
        def __init__(self, url, **kwargs):
            self.url = url

        async def __aenter__(self):
            return _Rpc(self.url)

        async def __aexit__(self, exc_type, exc, tb):
            return None

    runtime = RuntimePrimaryScanFacade()
    runtime.rpc_manager = _Manager()
    runtime.cfg = SimpleNamespace(execution=SimpleNamespace(flash_provider="aave"))
    monkeypatch.setattr(runtime, "_build_provider_comparison_pool_event_cache", lambda *args, **kwargs: object())

    async def fake_discovery(rpc, *, current_block):
        return {"v3_pairs": [], "curve_pools": [], "balancer_pools": []}

    async def fake_fee_observation(*args, **kwargs):
        return {"ok": True, "fee_bps": 9, "status": "ok"}

    async def fake_token_amounts(*args, **kwargs):
        return {"weth": 1000}, {"enabled": True, "amounts_by_token": {"weth": "1000"}}

    runtime._build_token_scan_amounts = fake_token_amounts
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.observe_flashloan_fee_bps",
        fake_fee_observation,
    )

    async def fake_token_amounts(*args, **kwargs):
        return {"weth": 1000}, {"enabled": True, "amounts_by_token": {"weth": "1000"}}

    async def fake_scan(
        rpc,
        *,
        current_block,
        amount_in,
        cache,
        discovery_context,
        telemetry_sink,
        shared_token_scan_amounts=None,
        force_adaptive_size_scan=False,
    ):
        profit = 100 if rpc.url.endswith("a.example") else 300
        telemetry_sink.update(
            {
                "quotes": {"requests": 10, "successes": 10, "failure_reasons": {}},
                "scan_latency_ms": 1.0,
                "provider_comparison_cost_inputs": {
                                    "block_number": 123,
                                    "base_amount_in": str(int(amount_in)),
                                    "gas_price_wei": "100",
                                    "gas_price_status": "consensus",
                                    "flashloan_fee_bps": "9",
                                    "flashloan_fee_ok": True,
                                    "flashloan_fee_status": "ok",
                                },
                "route_universe": {"edges_by_dex": {"univ3": 2}},
                "scan_sizing": {"amounts_by_token": {"weth": "1000"}},
                "adaptive_size_discovery": {"amounts_scanned": ["1000", "2000"]},
            }
        )
        return [
            SimpleNamespace(
                meta={
                    "canonical_after_fee_usd": {
                        "verified": True,
                        "profit_after_costs_usd_micro": profit,
                    }
                }
            )
        ]

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.JsonRpcClient",
        _Client,
    )
    monkeypatch.setattr(runtime, "_build_discovery_context", fake_discovery)
    monkeypatch.setattr(runtime, "_scan_primary_opportunities", fake_scan)

    result = await runtime._select_rpc_and_scan(
        bootstrap_rpc=_Rpc("https://rpc-a.example"),
        current_block=123,
        amount_in=1_000,
    )

    assert result["selected_endpoint"] == "https://rpc-b.example"
    assert result["opps"][0].meta["canonical_after_fee_usd"]["profit_after_costs_usd_micro"] == 300
    selection = result["telemetry"]["rpc"]["economic_selection"]
    assert selection["selected_endpoint"] == "https://rpc-b.example"
    assert selection["broadcast_attempted"] is False
    assert selection["auto_trade_enabled"] is False
    symmetry = selection["provider_scan_symmetry"]
    assert symmetry["route_universe_identical"] is True
    assert symmetry["size_ladder_identical"] is True
    assert symmetry["token_size_ladder_identical"] is True
    assert symmetry["failed_quotes_are_non_candidates"] is True
    assert {url for url, _ in runtime.rpc_manager.telemetry} == {
        "https://rpc-a.example",
        "https://rpc-b.example",
    }

@pytest.mark.asyncio
async def test_rpc_selection_publishes_inflight_provider_progress(monkeypatch):
    class _Manager:
        def read_candidates(self):
            return ["https://rpc-a.example"]

        def observe_quote_telemetry(self, url, **kwargs):
            return None

        def snapshot(self):
            return {
                "read": [
                    {"url": "https://rpc-a.example", "ok": True, "score": 10.0},
                ]
            }

    runtime = RuntimePrimaryScanFacade()
    runtime.rpc_manager = _Manager()
    runtime.cfg = SimpleNamespace()
    runtime.cache = PerBlockCache()
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MIN_OPPORTUNITIES", "1")
    monkeypatch.setattr(
        runtime,
        "_build_provider_comparison_pool_event_cache",
        lambda *args, **kwargs: object(),
    )

    async def fake_discovery(rpc, *, current_block):
        return {"v3_pairs": [], "curve_pools": [], "balancer_pools": [], "runtime": {}}

    async def fake_token_amounts(*args, **kwargs):
        return {"weth": 1000}, {"amounts_by_token": {"weth": "1000"}}

    scan_started = asyncio.Event()
    release_scan = asyncio.Event()
    candidate = SimpleNamespace(
        id="route-id",
        route_id="route-profitable",
        strategy="two-leg:univ3->sushiswap-v2",
        expected_profit_raw="20",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="1000")]),
        meta={
            "profitability": {
                "revalidated": True,
                "authoritative": True,
                "valid": True,
                "repayment_valid": True,
                "profit_after_costs_wei": "10",
            },
            "canonical_after_fee_usd": {
                "verified": True,
                "profit_after_costs_usd_micro": 10,
            },
        },
    )

    async def fake_scan(
        rpc,
        *,
        current_block,
        amount_in,
        cache,
        discovery_context,
        telemetry_sink,
        shared_token_scan_amounts,
        force_adaptive_size_scan,
    ):
        scan_started.set()
        await release_scan.wait()
        telemetry_sink.update({
            "quotes": {"requests": 4, "successes": 4, "failure_reasons": {}},
            "scan_latency_ms": 10.0,
            "route_universe": {"edges_by_dex": {"univ3": 2}},
            "scan_sizing": {"amounts_by_token": {"weth": "1000"}},
            "adaptive_size_discovery": {"amounts_scanned": ["1000"]},
        })
        return [candidate]

    async def fake_size_probe(
        rpc,
        *,
        current_block,
        base_amount_in,
        base_opps,
        cache,
    ):
        return list(base_opps), {
            "adaptive_size_discovery": {
                "amounts_scanned": ["1000"],
                "probe_triggered": False,
                "economic_matrix_complete": True,
            },
            "size_economic_matrix": [
                {"amount_in": "1000", "candidates": []},
            ],
            "size_economic_evidence": [],
        }

    runtime._build_discovery_context = fake_discovery
    runtime._build_token_scan_amounts = fake_token_amounts
    runtime._scan_primary_opportunities = fake_scan
    runtime._run_bounded_selected_provider_size_probe = fake_size_probe

    task = asyncio.create_task(runtime._select_rpc_and_scan(
        bootstrap_rpc=SimpleNamespace(url="https://rpc-a.example"),
        current_block=123,
        amount_in=1000,
    ))
    await asyncio.wait_for(scan_started.wait(), timeout=2.0)

    in_flight = dict(runtime._market_pipeline_telemetry["rpc_selection_progress"])
    assert in_flight["phase"] == "provider_comparison"
    assert in_flight["providers_running"] == 1
    assert in_flight["providers_completed"] == 0
    assert in_flight["providers"][0]["provider"] == "rpc-a.example"
    assert in_flight["providers"][0]["status"] == "running"
    assert "https://" not in str(in_flight)

    release_scan.set()
    result = await asyncio.wait_for(task, timeout=5.0)
    finished = result["telemetry"]["rpc_selection_progress"]
    assert finished["phase"] == "complete"
    assert finished["providers_completed"] == 1
    assert finished["providers_failed"] == 0
    assert finished["providers"][0]["candidate_count"] == 1


@pytest.mark.asyncio
async def test_runtime_rpc_race_preserves_selected_adaptive_telemetry_without_candidates(monkeypatch):
    class _Manager:
        def __init__(self):
            self.telemetry = []

        def read_candidates(self):
            return ["https://rpc-a.example"]

        def observe_quote_telemetry(self, url, **kwargs):
            self.telemetry.append((url, kwargs))

        def snapshot(self):
            return {
                "read": [
                    {"url": "https://rpc-a.example", "ok": True, "score": 10.0},
                ]
            }

    class _Rpc:
        def __init__(self, url):
            self.url = url

    runtime = RuntimePrimaryScanFacade()
    runtime.rpc_manager = _Manager()
    runtime.cfg = SimpleNamespace()
    monkeypatch.setattr(runtime, "_build_provider_comparison_pool_event_cache", lambda *args, **kwargs: object())

    async def fake_discovery(rpc, *, current_block):
        return {"v3_pairs": [], "curve_pools": [], "balancer_pools": [], "runtime": {}}

    selected_probe_calls = []

    async def fake_scan(
        rpc,
        *,
        current_block,
        amount_in,
        cache,
        discovery_context,
        telemetry_sink,
        shared_token_scan_amounts=None,
        force_adaptive_size_scan=False,
    ):
        telemetry_sink.update({
            "quotes": {"requests": 7, "successes": 7, "failure_reasons": {}},
            "scan_latency_ms": 2.0,
            "route_universe": {"edges_by_dex": {"univ3": 2}},
            "scan_sizing": {"amounts_by_token": {"weth": "1000"}},
        })
        return []

    async def fake_selected_probe(
        rpc,
        *,
        current_block,
        base_amount_in,
        base_opps,
        cache,
    ):
        selected_probe_calls.append((rpc.url, list(base_opps), int(base_amount_in)))
        return [], {
            "adaptive_size_discovery": {
                "enabled": True,
                "amounts_scanned": ["1000", "500", "1500", "2000"],
                "probe_triggered": True,
                "economic_matrix_complete": True,
            },
            "size_economic_matrix": [
                {"amount_in": "1000", "economic_optimum_after_cost_profit_wei": "0"},
            ],
            "size_economic_evidence": [],
        }

    runtime._build_discovery_context = fake_discovery
    runtime._scan_primary_opportunities = fake_scan
    runtime._run_bounded_selected_provider_size_probe = fake_selected_probe
    runtime.cache = object()

    result = await runtime._select_rpc_and_scan(
        bootstrap_rpc=_Rpc("https://rpc-a.example"),
        current_block=123,
        amount_in=1_000,
    )

    assert selected_probe_calls == [("https://rpc-a.example", [], 1_000)]
    telemetry = result["telemetry"]
    assert telemetry["adaptive_size_discovery"]["amounts_scanned"] == [
        "1000", "500", "1500", "2000"
    ]
    assert telemetry["selected_provider_adaptive"]["adaptive_size_discovery"]["probe_triggered"] is True
    assert telemetry["size_economic_matrix"][0]["economic_optimum_after_cost_profit_wei"] == "0"
    assert result["opps"] == []


@pytest.mark.asyncio
async def test_bounded_selected_provider_sizing_probes_promising_routes_only(monkeypatch):
    runtime = RuntimePrimaryScanFacade()
    runtime.cfg = SimpleNamespace(
        safety=SimpleNamespace(slippage_bps=50),
    )

    class _Manager:
        async def gas_price_consensus(self):
            return {
                "gas_price_wei": 1,
                "status": "consensus",
                "observations": [],
                "anomalies": [],
            }

    runtime.rpc_manager = _Manager()
    monkeypatch.setattr(runtime, "_adaptive_scan_amounts", lambda amount, **kwargs: [amount, amount // 2, amount * 2])
    async def noop_annotate(*args, **kwargs):
        return None
    monkeypatch.setattr(runtime, "_annotate_canonical_after_fee_usd", noop_annotate)

    class _Candidate:
        def __init__(self, amount_in="1000", profit="100"):
            self.id = "base"
            self.route_id = "route-base"
            self.strategy = "two-leg:univ3->univ3"
            self.expected_profit_raw = str(profit)
            self.route = SimpleNamespace(
                legs=[SimpleNamespace(amount_in=str(amount_in))]
            )
            self.meta = {
                "route_edge_params": [
                    {"fee": 500},
                    {"fee": 3000},
                ],
                "profitability": {
                    "revalidated": True,
                    "authoritative": False,
                    "profit_after_costs_wei": "-1",
                },
            }

        def model_copy(self, *, deep=True):
            return _Candidate(
                amount_in=self.route.legs[0].amount_in,
                profit=self.expected_profit_raw,
            )

    base = _Candidate()

    async def fake_requote(rpc, cfg, cache, candidate, *, new_amount_in, slippage_bps):
        candidate.route.legs[0].amount_in = str(new_amount_in)
        candidate.expected_profit_raw = str(new_amount_in // 10)
        return candidate

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.requote_opportunity",
        fake_requote,
    )

    sized, telemetry = await runtime._run_bounded_selected_provider_size_probe(
        object(),
        current_block=123,
        base_amount_in=1_000,
        base_opps=[base],
        cache=PerBlockCache(),
    )

    assert len(sized) == 3
    adaptive = telemetry["adaptive_size_discovery"]
    assert adaptive["probe_triggered"] is True
    assert adaptive["amounts_scanned"] == ["500", "1000", "2000"]
    assert adaptive["selected_route_count"] == 1


@pytest.mark.asyncio
async def test_runtime_rpc_race_preserves_healthy_provider_opportunity_union(monkeypatch):
    class _Manager:
        def __init__(self):
            self.telemetry = []

        def read_candidates(self):
            return ["https://rpc-a.example", "https://rpc-b.example"]

        def observe_quote_telemetry(self, url, **kwargs):
            self.telemetry.append((url, kwargs))

        async def gas_price_consensus(self):
            return {"gas_price_wei": 100, "status": "consensus", "observations": [], "anomalies": []}

        def snapshot(self):
            return {
                "read": [
                    {"url": "https://rpc-a.example", "ok": True, "score": 10.0},
                    {"url": "https://rpc-b.example", "ok": True, "score": 20.0},
                ]
            }

    class _Rpc:
        def __init__(self, url):
            self.url = url

    class _Client:
        def __init__(self, url, **kwargs):
            self.url = url

        async def __aenter__(self):
            return _Rpc(self.url)

        async def __aexit__(self, exc_type, exc, tb):
            return None

    runtime = RuntimePrimaryScanFacade()
    runtime.rpc_manager = _Manager()
    runtime.cfg = SimpleNamespace(execution=SimpleNamespace(flash_provider="aave"))
    monkeypatch.setattr(runtime, "_build_provider_comparison_pool_event_cache", lambda *args, **kwargs: object())

    async def fake_discovery(rpc, *, current_block):
        return {"v3_pairs": [], "curve_pools": [], "balancer_pools": []}

    async def fake_fee_observation(*args, **kwargs):
        return {"ok": True, "fee_bps": 9, "status": "ok"}

    async def fake_token_amounts(*args, **kwargs):
        return {"weth": 1000}, {"enabled": True, "amounts_by_token": {"weth": "1000"}}

    runtime._build_token_scan_amounts = fake_token_amounts
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.observe_flashloan_fee_bps",
        fake_fee_observation,
    )

    async def fake_token_amounts(*args, **kwargs):
        return {"weth": 1000}, {"enabled": True, "amounts_by_token": {"weth": "1000"}}

    async def fake_scan(
        rpc,
        *,
        current_block,
        amount_in,
        cache,
        discovery_context,
        telemetry_sink,
        shared_token_scan_amounts=None,
        force_adaptive_size_scan=False,
    ):
        telemetry_sink.update({
            "quotes": {"requests": 10, "successes": 10, "failure_reasons": {}},
            "scan_latency_ms": 1.0,
            "provider_comparison_cost_inputs": {
                                "block_number": 123,
                                "base_amount_in": str(int(amount_in)),
                                "gas_price_wei": "100",
                                "gas_price_status": "consensus",
                                "flashloan_fee_bps": "9",
                                "flashloan_fee_ok": True,
                                "flashloan_fee_status": "ok",
                            },
            "route_universe": {"edges_by_dex": {"univ3": 2}},
            "scan_sizing": {"amounts_by_token": {"weth": "1000"}},
            "adaptive_size_discovery": {"amounts_scanned": ["1000", "2000"]},
        })
        suffix = "a" if rpc.url.endswith("a.example") else "b"

        def opp(route_id, profit):
            return SimpleNamespace(
                id=f"id-{route_id}",
                route_id=route_id,
                expected_profit_raw=str(profit),
                route=SimpleNamespace(
                    legs=[SimpleNamespace(amount_in="1000")]
                ),
                meta={
                    "canonical_after_fee_usd": {
                        "verified": True,
                        "profit_after_costs_usd_micro": profit,
                    }
                },
            )

        if suffix == "a":
            return [opp("shared", 100), opp("only-a", 150)]
        return [opp("shared", 300), opp("only-b", 250)]

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.JsonRpcClient",
        _Client,
    )
    monkeypatch.setattr(runtime, "_build_discovery_context", fake_discovery)
    monkeypatch.setattr(runtime, "_scan_primary_opportunities", fake_scan)

    result = await runtime._select_rpc_and_scan(
        bootstrap_rpc=_Rpc("https://rpc-a.example"),
        current_block=123,
        amount_in=1_000,
    )

    routes = {opp.route_id for opp in result["opps"]}
    assert routes == {"shared", "only-a", "only-b"}
    shared = next(opp for opp in result["opps"] if opp.route_id == "shared")
    assert shared.meta["canonical_after_fee_usd"]["profit_after_costs_usd_micro"] == 300
    assert shared.meta["quote_provider"] == "rpc-b.example"
    assert result["selected_endpoint"] == "https://rpc-b.example"


@pytest.mark.asyncio
async def test_canonical_after_fee_usd_preserves_negative_observed_economics(monkeypatch):
    runtime = RuntimePrimaryScanFacade()
    runtime.cache = PerBlockCache()
    runtime.cfg = SimpleNamespace(
        execution=SimpleNamespace(
            usd_accounting_enabled=True,
            usd_stable_preference="usdc",
            flash_provider="aave",
        ),
        chain=SimpleNamespace(chain_id=1),
    )

    class _Rpc:
        async def gas_price(self):
            return 1

    async def fake_flash(*args, **kwargs):
        return {"ok": True, "fee_bps": 9}

    async def fake_usd(*args, **kwargs):
        assert kwargs["amount_wei"] == 250
        return 500

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.observe_flashloan_fee_bps",
        fake_flash,
    )
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.token_to_usd_micro",
        fake_usd,
    )
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.estimate_route_gas_units",
        lambda meta: 0,
    )
    async def fake_gas(*args, **kwargs):
        return 0
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.gas_wei_to_token_wei",
        fake_gas,
    )

    opportunity = SimpleNamespace(
        expected_profit_raw="-250",
        route=SimpleNamespace(
            legs=[SimpleNamespace(token_in="0xprofit", token_out="0xother", amount_in=1000, min_out=1, dex="univ3", venue="test")],
        ),
        meta={
            "gas_cost_estimate_wei": "0",
            "profitability": {
                "revalidated": True,
                "authoritative": True,
                "valid": True,
                "profit_after_costs_wei": "-250",
                "gas_cost_wei": "0",
                "flashloan_fee_wei": "0",
            },
            "venues": ["univ3"],
        },
    )
    await runtime._annotate_canonical_after_fee_usd(
        opps=[opportunity],
        rpc=_Rpc(),
        current_block=1,
    )
    assert opportunity.meta["canonical_after_fee_usd"]["profit_after_costs_usd_micro"] == "-500"


@pytest.mark.asyncio
async def test_runtime_rpc_race_bounds_slow_provider_without_blocking_fast_provider(monkeypatch):
    monkeypatch.setenv("VICTOR_RPC_PROVIDER_SCAN_TIMEOUT_S", "0.25")

    class _Manager:
        def __init__(self):
            self.telemetry = []

        def read_candidates(self):
            return ["https://rpc-fast.example", "https://rpc-slow.example"]

        def observe_quote_telemetry(self, url, **kwargs):
            self.telemetry.append((url, kwargs))

        def snapshot(self):
            return {
                "read": [
                    {"url": "https://rpc-fast.example", "ok": True, "score": 10.0},
                    {"url": "https://rpc-slow.example", "ok": True, "score": 20.0},
                ]
            }

    class _Rpc:
        def __init__(self, url):
            self.url = url

    class _Client:
        def __init__(self, url, **kwargs):
            self.url = url

        async def __aenter__(self):
            return _Rpc(self.url)

        async def __aexit__(self, exc_type, exc, tb):
            return None

    runtime = RuntimePrimaryScanFacade()
    runtime.rpc_manager = _Manager()
    runtime.cfg = SimpleNamespace()
    monkeypatch.setattr(runtime, "_build_provider_comparison_pool_event_cache", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime, "_provider_scan_timeout_s", lambda: 0.25)

    async def fake_discovery(rpc, *, current_block):
        return {"v3_pairs": [], "curve_pools": [], "balancer_pools": []}

    async def fake_scan(
        rpc,
        *,
        current_block,
        amount_in,
        cache,
        discovery_context,
        telemetry_sink,
        shared_token_scan_amounts=None,
        force_adaptive_size_scan=False,
    ):
        if rpc.url.endswith("slow.example"):
            await asyncio.sleep(1.0)
        telemetry_sink.update({
            "quotes": {"requests": 4, "successes": 4, "failure_reasons": {}},
            "scan_latency_ms": 1.0,
            "route_universe": {"edges_by_dex": {"univ3": 1}},
            "scan_sizing": {"amounts_by_token": {"weth": "1000"}},
            "adaptive_size_discovery": {"amounts_scanned": ["1000"]},
        })
        return [
            SimpleNamespace(
                meta={
                    "canonical_after_fee_usd": {
                        "verified": True,
                        "profit_after_costs_usd_micro": 500,
                    }
                }
            )
        ]

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.JsonRpcClient",
        _Client,
    )
    monkeypatch.setattr(runtime, "_build_discovery_context", fake_discovery)
    monkeypatch.setattr(runtime, "_scan_primary_opportunities", fake_scan)

    result = await runtime._select_rpc_and_scan(
        bootstrap_rpc=_Rpc("https://rpc-fast.example"),
        current_block=123,
        amount_in=1_000,
    )

    assert result["selected_endpoint"] == "https://rpc-fast.example"
    slow = next(
        item for item in result["evidence"]
        if str(item.endpoint).endswith("slow.example")
    )
    assert slow.healthy is False
    assert slow.scan_latency_ms >= 250.0
    assert result["telemetry"]["rpc_selection_phase"] == "complete"


@pytest.mark.asyncio
async def test_rpc_manager_probe_interval_timeout_keeps_loop_alive():
    manager = RpcManager(
        rpc_read=["https://rpc.example"],
        rpc_send=["https://rpc.example"],
        probe_interval_s=0.01,
    )
    calls = 0

    async def fake_probe(url, stats):
        nonlocal calls
        calls += 1

    manager._probe_one = fake_probe
    task = asyncio.create_task(manager._loop())
    await asyncio.sleep(0.04)
    manager._stop.set()
    await asyncio.wait_for(task, timeout=0.2)

    assert calls >= 2



def test_effective_flashloan_fee_prefers_provider_observation():
    from victor_ai_bot.execution import _effective_flashloan_fee_bps

    assert _effective_flashloan_fee_bps(12, 9) == 12
    assert _effective_flashloan_fee_bps(None, 9) == 9


def test_best_read_excludes_quote_quarantined_provider():
    manager = RpcManager(
        rpc_read=["https://rpc-a.example", "https://rpc-b.example"],
        rpc_send=["https://rpc-a.example", "https://rpc-b.example"],
    )
    manager._read["https://rpc-a.example"].last_seen_block = 100
    manager._read["https://rpc-b.example"].last_seen_block = 100
    manager._read["https://rpc-a.example"].quote_unhealthy_until = 9_999_999_999.0

    assert manager.best_read() == "https://rpc-b.example"
    manager._read["https://rpc-b.example"].quote_unhealthy_until = 9_999_999_999.0
    assert manager.best_read() == ""
