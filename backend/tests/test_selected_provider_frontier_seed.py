from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.config import load_config
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    RuntimePrimaryScanFacade,
)


def test_selected_provider_full_scan_budget_scales_with_graph_and_reserves_frontier(monkeypatch):
    runtime = RuntimePrimaryScanFacade()
    monkeypatch.delenv("VICTOR_SELECTED_PROVIDER_FULL_SCAN_BUDGET_S", raising=False)
    monkeypatch.delenv("VICTOR_SELECTED_PROVIDER_FULL_SCAN_CHUNK_SIZE", raising=False)
    monkeypatch.delenv("VICTOR_SELECTED_PROVIDER_FULL_SCAN_PARALLELISM", raising=False)

    baseline = runtime._selected_provider_full_scan_budget_s(235)
    dense_graph = runtime._selected_provider_full_scan_budget_s(370)

    assert baseline == 28.0
    assert dense_graph == 35.5
    assert dense_graph > baseline
    assert runtime._selected_provider_frontier_seed_budget_s() == 8.0

    monkeypatch.setenv("VICTOR_SELECTED_PROVIDER_FULL_SCAN_BUDGET_S", "44")
    assert runtime._selected_provider_full_scan_budget_s(10_000) == 45.0
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_FRONTIER_SEED_BUDGET_S", "99")
    assert runtime._selected_provider_frontier_seed_budget_s() == 12.0


def test_selected_provider_chunk_accounting_covers_completed_timeout_failed_and_skipped():
    from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
        _selected_provider_chunk_accounting,
    )

    accounting = _selected_provider_chunk_accounting(
        graph_edge_count=58,
        chunk_size=16,
        chunk_statuses={
            0: "completed",
            1: "timed_out",
            2: "failed",
            3: "pending",
        },
        chunk_status_reasons={1: "chunk_timeout", 2: "rpc_error"},
    )

    assert accounting["chunks_accounted"] == 4
    assert accounting["chunks_timed_out"] == 1
    assert accounting["chunks_failed"] == 1
    assert accounting["chunks_skipped"] == 1
    rows = accounting["chunk_accounting"]
    assert [row["edges"] for row in rows] == [16, 16, 16, 10]
    assert [row["status"] for row in rows] == [
        "completed", "timed_out", "failed", "skipped_budget"
    ]
    assert rows[1]["reason"] == "chunk_timeout"
    assert rows[3]["reason"] == "budget_exhausted_before_schedule"


def test_selected_provider_full_scan_chunk_size_is_bounded(monkeypatch):
    runtime = RuntimePrimaryScanFacade()
    env_name = "VICTOR_SELECTED_PROVIDER_FULL_SCAN_CHUNK_SIZE"

    assert runtime._selected_provider_full_scan_chunk_size() == 16

    monkeypatch.setenv(env_name, "8")
    assert runtime._selected_provider_full_scan_chunk_size() == 8

    monkeypatch.setenv(env_name, "4")
    assert runtime._selected_provider_full_scan_chunk_size() == 8

    monkeypatch.setenv(env_name, "99")
    assert runtime._selected_provider_full_scan_chunk_size() == 99

    monkeypatch.setenv(env_name, "999")
    assert runtime._selected_provider_full_scan_chunk_size() == 256

    monkeypatch.setenv(env_name, "invalid")
    assert runtime._selected_provider_full_scan_chunk_size() == 16

    monkeypatch.setenv(env_name, "")
    assert runtime._selected_provider_full_scan_chunk_size() == 16


@pytest.mark.asyncio
async def test_selected_provider_batch_waits_for_siblings_when_chunk_raises():
    from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
        _gather_selected_provider_scan_batch,
    )

    completed = []

    async def fail_unexpectedly():
        raise AssertionError("synthetic chunk failure")

    async def finish_after_yield():
        await asyncio.sleep(0)
        completed.append("sibling-finished")

    tasks = [
        asyncio.create_task(fail_unexpectedly()),
        asyncio.create_task(finish_after_yield()),
    ]
    errors = []
    await _gather_selected_provider_scan_batch(tasks, [4, 5], errors)

    assert completed == ["sibling-finished"]
    assert errors == [{
        "chunk": 4,
        "reason": "AssertionError: synthetic chunk failure",
    }]


def test_selected_provider_full_scan_parallelism_is_bounded(monkeypatch):
    runtime = RuntimePrimaryScanFacade()

    assert runtime._selected_provider_full_scan_parallelism() == 3

    monkeypatch.setenv("VICTOR_SELECTED_PROVIDER_FULL_SCAN_PARALLELISM", "2")
    assert runtime._selected_provider_full_scan_parallelism() == 2

    monkeypatch.setenv("VICTOR_SELECTED_PROVIDER_FULL_SCAN_PARALLELISM", "99")
    assert runtime._selected_provider_full_scan_parallelism() == 3

    monkeypatch.setenv("VICTOR_SELECTED_PROVIDER_FULL_SCAN_PARALLELISM", "0")
    assert runtime._selected_provider_full_scan_parallelism() == 1

    monkeypatch.setenv("VICTOR_SELECTED_PROVIDER_FULL_SCAN_PARALLELISM", "invalid")
    assert runtime._selected_provider_full_scan_parallelism() == 3


def test_selected_provider_frontier_seed_amounts_prioritize_nearby_sizes(monkeypatch):
    runtime = RuntimePrimaryScanFacade()
    monkeypatch.setenv(
        "VICTOR_ADAPTIVE_SIZE_FRONTIER_SEED_MULTIPLIERS",
        "1.5,2.0,0.5",
    )
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_FRONTIER_SEED_MAX_PROBES", "3")

    monkeypatch.setattr(
        runtime,
        "_adaptive_scan_amounts",
        lambda amount, **kwargs: [
            int(amount),
            int(amount) // 2,
            int(round(int(amount) * 1.5)),
            int(amount) * 2,
            int(amount) * 4,
        ],
    )

    assert runtime._selected_provider_frontier_seed_amounts(1_000) == [
        1_500,
        2_000,
        500,
    ]


@pytest.mark.asyncio
async def test_selected_provider_frontier_seed_discovers_route_missing_at_base_size(monkeypatch):
    class Manager:
        def read_candidates(self):
            return ["https://rpc.example"]

        def observe_quote_telemetry(self, url, **kwargs):
            return None

        def snapshot(self):
            return {
                "read": [
                    {
                        "url": "https://rpc.example",
                        "ok": True,
                        "score": 10.0,
                    }
                ]
            }

    candidate = SimpleNamespace(
        id="seed-id",
        route_id="seed-route",
        strategy="two-leg:univ3->univ3",
        expected_profit_raw="5270",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(
                    amount_in="1500",
                )
            ]
        ),
        meta={
            "canonical_after_fee_usd": {
                "profit_after_costs_usd_micro": 1,
            }
        },
    )

    runtime = RuntimePrimaryScanFacade()
    runtime.rpc_manager = Manager()
    runtime.cfg = SimpleNamespace()
    runtime.cache = object()

    async def fake_discovery(*args, **kwargs):
        return {"v3_pairs": [], "curve_pools": [], "balancer_pools": [], "runtime": {}}

    async def fake_token_amounts(*args, **kwargs):
        return {"weth": 1000}, {
            "enabled": True,
            "source": "test",
            "amounts_by_token": {"weth": "1000"},
        }

    scan_amounts = []
    provider_comparison_flags = []
    full_graph_base_only_flags = []

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
        scan_amounts.append(int(amount_in))
        provider_comparison_flags.append(
            bool(getattr(runtime, "_rpc_provider_comparison", False))
        )
        full_graph_base_only_flags.append(
            bool(
                (discovery_context or {}).get(
                    "_selected_provider_full_graph_base_only"
                )
            )
        )
        telemetry_sink.update(
            {
                "quotes": {"requests": 10, "successes": 10, "failure_reasons": {}},
                "scan_latency_ms": 1.0,
                "route_universe": {"edges_by_dex": {"univ3": 2}},
                "scan_sizing": {
                    "amounts_by_token": {
                        "weth": str(int(amount_in)),
                    }
                },
                "adaptive_size_discovery": {
                    "amounts_scanned": [str(int(amount_in))]
                },
            }
        )
        return [candidate] if int(amount_in) == 1500 else []

    probe_calls = []

    async def fake_probe(
        rpc,
        *,
        current_block,
        base_amount_in,
        base_opps,
        cache,
    ):
        probe_calls.append(list(base_opps))
        return list(base_opps), {
            "adaptive_size_discovery": {
                "amounts_scanned": ["1000", "500", "1500", "2000"],
                "probe_triggered": True,
            },
            "size_economic_matrix": [],
            "size_economic_evidence": [],
        }

    runtime._build_discovery_context = fake_discovery
    runtime._build_provider_comparison_pool_event_cache = lambda *args, **kwargs: object()
    runtime._build_token_scan_amounts = fake_token_amounts
    runtime._scan_primary_opportunities = fake_scan
    runtime._run_bounded_selected_provider_size_probe = fake_probe

    result = await runtime._select_rpc_and_scan(
        bootstrap_rpc=SimpleNamespace(url="https://rpc.example"),
        current_block=123,
        amount_in=1000,
    )

    assert scan_amounts == [1000, 1000, 1500, 2000, 500]
    assert provider_comparison_flags == [True, False, False, False, False]
    assert full_graph_base_only_flags == [False, True, True, True, True]
    assert len(probe_calls) == 1
    assert [opp.route_id for opp in probe_calls[0]] == ["seed-route"]
    assert [opp.route_id for opp in result["opps"]] == ["seed-route"]
    assert result["telemetry"]["selected_provider_adaptive"]["adaptive_size_discovery"]["frontier_seed"]["candidates_added"] == 1


@pytest.mark.asyncio
async def test_frontier_seed_reference_preserves_absolute_size_targets(monkeypatch):
    runtime = RuntimePrimaryScanFacade()
    runtime.cfg = SimpleNamespace(
        safety=SimpleNamespace(slippage_bps=50),
    )

    class Manager:
        async def gas_price_consensus(self):
            return {
                "gas_price_wei": 1,
                "status": "consensus",
                "observations": [],
                "anomalies": [],
            }

    runtime.rpc_manager = Manager()
    monkeypatch.setattr(
        runtime,
        "_adaptive_scan_amounts",
        lambda amount, **kwargs: [1000, 500, 1500, 2000],
    )
    async def noop_annotate(*args, **kwargs):
        return None

    monkeypatch.setattr(
        runtime,
        "_annotate_canonical_after_fee_usd",
        noop_annotate,
    )

    class Candidate:
        def __init__(self, amount_in="1500"):
            self.id = "seed"
            self.route_id = "seed-route"
            self.strategy = "two-leg:univ3->univ3"
            self.expected_profit_raw = "5270"
            self.route = SimpleNamespace(
                legs=[SimpleNamespace(amount_in=str(amount_in))]
            )
            self.meta = {
                "adaptive_seed_amount_in": "1500",
                "profitability": {
                    "revalidated": True,
                    "authoritative": False,
                    "profit_after_costs_wei": "-1",
                },
            }

        def model_copy(self, *, deep=True):
            return Candidate(self.route.legs[0].amount_in)

    seen = []

    async def fake_requote(
        rpc,
        cfg,
        cache,
        candidate,
        *,
        new_amount_in,
        slippage_bps,
    ):
        seen.append(int(new_amount_in))
        candidate.route.legs[0].amount_in = str(int(new_amount_in))
        return candidate

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_primary_scan_facade.requote_opportunity",
        fake_requote,
    )

    await runtime._run_bounded_selected_provider_size_probe(
        object(),
        current_block=123,
        base_amount_in=1000,
        base_opps=[Candidate()],
        cache=object(),
    )

    assert seen == [500, 1500, 2000]


def test_frozen_provider_graph_slice_preserves_stable_edge_order():
    from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
        _FrozenProviderScanPoolEventCache,
    )

    edges = ["e0", "e1", "e2", "e3"]
    cache = _FrozenProviderScanPoolEventCache(
        edges,
        {
            "candidate_edges_full": 4,
            "candidate_edge_count": 4,
        },
        {id(edge): index + 1 for index, edge in enumerate(edges)},
    )

    sliced = cache.slice(1, 2)

    assert cache.edge_count() == 4
    assert sliced.edge_count() == 2
    assert sliced.candidate_edges(
        [],
        current_block=123,
    )[0] == ["e1", "e2"]
    assert sliced.route_universe_edges() == edges
    assert sliced.edge_priority("e1", current_block=123) == 2
    assert sliced.edge_priority("e2", current_block=123) == 3


def test_chain_scoped_execution_envelope_overrides_yaml(tmp_path, monkeypatch):
    cfg_path = tmp_path / "base.yaml"
    cfg_path.write_text(
        """
chain:
  name: base
  chain_id: 8453
execution:
  executor_address: ""
  profit_to: ""
""",
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "VICTOR_BASE_EXECUTOR_ADDRESS",
        "0x1111111111111111111111111111111111111111",
    )
    monkeypatch.setenv(
        "VICTOR_BASE_PROFIT_TO",
        "0x2222222222222222222222222222222222222222",
    )

    cfg = load_config(str(cfg_path))

    assert cfg.execution.executor_address == "0x1111111111111111111111111111111111111111"
    assert cfg.execution.profit_to == "0x2222222222222222222222222222222222222222"
