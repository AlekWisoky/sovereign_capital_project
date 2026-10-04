from __future__ import annotations

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


@pytest.mark.asyncio
async def test_runtime_rpc_race_selects_higher_economic_provider_without_broadcast(monkeypatch):
    class _Manager:
        def __init__(self):
            self.telemetry = []

        def read_candidates(self):
            return ["https://rpc-a.example", "https://rpc-b.example"]

        def observe_quote_telemetry(self, url, **kwargs):
            self.telemetry.append((url, kwargs))

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
    runtime.cfg = SimpleNamespace()

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
        profit = 100 if rpc.url.endswith("a.example") else 300
        telemetry_sink.update(
            {
                "quotes": {"requests": 10, "successes": 10, "failure_reasons": {}},
                "scan_latency_ms": 1.0,
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

    async def fake_discovery(rpc, *, current_block):
        return {"v3_pairs": [], "curve_pools": [], "balancer_pools": [], "runtime": {}}

    calls = []

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
        calls.append(bool(force_adaptive_size_scan))
        telemetry_sink.update({
            "quotes": {"requests": 7, "successes": 7, "failure_reasons": {}},
            "scan_latency_ms": 2.0,
            "route_universe": {"edges_by_dex": {"univ3": 2}},
            "scan_sizing": {"amounts_by_token": {"weth": "1000"}},
            "adaptive_size_discovery": {
                "enabled": True,
                "amounts_scanned": ["1000", "500", "1500", "2000", "4000", "8000", "16000"],
                "probe_triggered": True,
                "economic_matrix_complete": True,
            },
            "size_economic_matrix": [
                {"amount_in": "1000", "economic_optimum_after_cost_profit_wei": "0"},
            ],
            "size_economic_evidence": [],
        })
        return []

    runtime._build_discovery_context = fake_discovery
    runtime._scan_primary_opportunities = fake_scan
    runtime.cache = object()

    result = await runtime._select_rpc_and_scan(
        bootstrap_rpc=_Rpc("https://rpc-a.example"),
        current_block=123,
        amount_in=1_000,
    )

    assert calls == [False, True]
    telemetry = result["telemetry"]
    assert telemetry["adaptive_size_discovery"]["amounts_scanned"] == [
        "1000", "500", "1500", "2000", "4000", "8000", "16000"
    ]
    assert telemetry["selected_provider_adaptive"]["adaptive_size_discovery"]["probe_triggered"] is True
    assert telemetry["size_economic_matrix"][0]["economic_optimum_after_cost_profit_wei"] == "0"
    assert result["opps"] == []


@pytest.mark.asyncio
async def test_runtime_rpc_race_preserves_healthy_provider_opportunity_union(monkeypatch):
    class _Manager:
        def __init__(self):
            self.telemetry = []

        def read_candidates(self):
            return ["https://rpc-a.example", "https://rpc-b.example"]

        def observe_quote_telemetry(self, url, **kwargs):
            self.telemetry.append((url, kwargs))

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
    runtime.cfg = SimpleNamespace()

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
        telemetry_sink.update({
            "quotes": {"requests": 10, "successes": 10, "failure_reasons": {}},
            "scan_latency_ms": 1.0,
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
    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.gas_wei_to_token_wei",
        fake_usd,
    )

    opportunity = SimpleNamespace(
        expected_profit_raw="-250",
        route=SimpleNamespace(legs=[]),
        meta={
            "gas_cost_estimate_wei": "0",
            "profitability": {
                "revalidated": True,
                "authoritative": False,
                "valid": True,
                "profit_after_costs_wei": "-250",
                "gas_cost_wei": "0",
                "flashloan_fee_wei": "0",
            },
            "venues": ["univ3"],
            },
        },
    )
    await runtime._annotate_canonical_after_fee_usd(
        opps=[opportunity],
        rpc=_Rpc(),
        current_block=1,
    )
    assert opportunity.meta["canonical_after_fee_usd"]["profit_after_costs_usd_micro"] == "-500"
