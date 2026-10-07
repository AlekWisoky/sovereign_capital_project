from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.config import load_config
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    RuntimePrimaryScanFacade,
)


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
    runtime._build_token_scan_amounts = fake_token_amounts
    runtime._scan_primary_opportunities = fake_scan
    runtime._run_bounded_selected_provider_size_probe = fake_probe

    result = await runtime._select_rpc_and_scan(
        bootstrap_rpc=SimpleNamespace(url="https://rpc.example"),
        current_block=123,
        amount_in=1000,
    )

    assert scan_amounts == [1000, 1500, 2000, 500]
    assert len(probe_calls) == 1
    assert [opp.route_id for opp in probe_calls[0]] == ["seed-route"]
    assert [opp.route_id for opp in result["opps"]] == ["seed-route"]
    assert result["telemetry"]["selected_provider_adaptive"]["frontier_seed"]["candidates_added"] == 1


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
