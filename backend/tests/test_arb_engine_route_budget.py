from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.arb_engine as arb


@pytest.mark.asyncio
async def test_two_leg_route_evaluation_survives_slow_first_quote_phase(monkeypatch):
    e1 = arb.Edge("univ3", "0x1111111111111111111111111111111111111111", "0x2222222222222222222222222222222222222222", "0x3333333333333333333333333333333333333333", {"fee": 3000})
    e2 = arb.Edge("univ3", "0x1111111111111111111111111111111111111111", "0x3333333333333333333333333333333333333333", "0x2222222222222222222222222222222222222222", {"fee": 3000})

    monkeypatch.setattr(arb, "build_edges", lambda *args, **kwargs: [e1, e2])

    async def fake_quotes(rpc, cfg, cache, edges, amount_in, metrics=None):
        if metrics is not None:
            metrics["quote_requests"] = int(metrics.get("quote_requests", 0)) + len(edges)
            metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + len(edges)
        result = {}
        for edge in edges:
            if edge == e1:
                result[arb.edge_key(edge)] = (110, {"gas_estimate": 1, "fee": 3000})
            elif edge == e2:
                result[arb.edge_key(edge)] = (120, {"gas_estimate": 1, "fee": 3000})
        return result

    monkeypatch.setattr(arb, "quote_edges_batch", fake_quotes)
    monkeypatch.setattr(
        arb,
        "scan_efficiency_snapshot",
        lambda **kwargs: {
            "elapsed_ms": 0.0,
            "candidate_count": int(kwargs["candidate_count"]),
            "quote_requests": int(kwargs["quote_requests"]),
            "quote_successes": int(kwargs["quote_successes"]),
            "quote_success_rate": 1.0,
            "cache_hits": 0,
            "network_batches": 1,
        },
    )

    cfg = SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        safety=SimpleNamespace(slippage_bps=50),
    )

    telemetry = {}
    out = await arb.find_two_leg_opportunities(
        object(),
        cfg,
        object(),
        123,
        amount_in=100,
        slippage_bps=50,
        time_budget_ms=1,
        telemetry=telemetry,
    )

    assert len(out) >= 1
    assert any(item.expected_profit_raw == "20" for item in out)
    assert telemetry["route_groups_evaluated"] >= 1
    assert telemetry["budget_exhausted_after_quote"] is False
    assert telemetry["route_universe"]["edges_by_dex"] == {"univ3": 2}
    assert telemetry["route_universe"]["unique_directed_pairs"] == 2
    assert telemetry["route_universe"]["directed_pairs_with_reverse"] == 2


@pytest.mark.asyncio
async def test_two_leg_route_budget_remains_bounded_after_first_group(monkeypatch):
    edges = [
        arb.Edge("univ3", "0x1111111111111111111111111111111111111111", "0x2222222222222222222222222222222222222222", "0x3333333333333333333333333333333333333333", {"fee": 3000}),
        arb.Edge("univ3", "0x1111111111111111111111111111111111111111", "0x3333333333333333333333333333333333333333", "0x2222222222222222222222222222222222222222", {"fee": 3000}),
        arb.Edge("univ3", "0x1111111111111111111111111111111111111111", "0x2222222222222222222222222222222222222222", "0x4444444444444444444444444444444444444444", {"fee": 3000}),
        arb.Edge("univ3", "0x1111111111111111111111111111111111111111", "0x4444444444444444444444444444444444444444", "0x2222222222222222222222222222222222222222", {"fee": 3000}),
    ]

    monkeypatch.setattr(arb, "build_edges", lambda *args, **kwargs: edges)

    async def fake_quotes(rpc, cfg, cache, requested_edges, amount_in, metrics=None):
        if metrics is not None:
            metrics["quote_requests"] = int(metrics.get("quote_requests", 0)) + len(requested_edges)
            metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + len(requested_edges)
        return {
            arb.edge_key(edge): (
                121
                if edge.token_out == "0x2222222222222222222222222222222222222222"
                else 120
                if edge.token_out
                in {
                    "0x3333333333333333333333333333333333333333",
                    "0x4444444444444444444444444444444444444444",
                }
                else 100,
                {"gas_estimate": 1, "fee": 3000},
            )
            for edge in requested_edges
        }

    monkeypatch.setattr(arb, "quote_edges_batch", fake_quotes)
    monkeypatch.setattr(
        arb,
        "scan_efficiency_snapshot",
        lambda **kwargs: {
            "elapsed_ms": 0.0,
            "candidate_count": int(kwargs["candidate_count"]),
            "quote_requests": int(kwargs["quote_requests"]),
            "quote_successes": int(kwargs["quote_successes"]),
            "quote_success_rate": 1.0,
            "cache_hits": 0,
            "network_batches": 1,
        },
    )

    # Force the route-evaluation clock to advance after the first group.
    clock = iter([0.0, 0.0, 0.0, 2.0])
    monkeypatch.setattr(arb.time, "perf_counter", lambda: next(clock, 2.0))

    cfg = SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        safety=SimpleNamespace(slippage_bps=50),
    )

    telemetry = {}
    out = await arb.find_two_leg_opportunities(
        object(),
        cfg,
        object(),
        123,
        amount_in=100,
        slippage_bps=50,
        time_budget_ms=1,
        telemetry=telemetry,
    )

    assert len(out) >= 1
    assert telemetry["route_groups_evaluated"] >= 1


@pytest.mark.asyncio
async def test_three_leg_route_evaluation_survives_slow_first_quote_phase(monkeypatch):
    a = "0x2222222222222222222222222222222222222222"
    b = "0x3333333333333333333333333333333333333333"
    c = "0x4444444444444444444444444444444444444444"
    edges = [
        arb.Edge("univ3", "0x1111111111111111111111111111111111111111", a, b, {"fee": 3000}),
        arb.Edge("univ3", "0x1111111111111111111111111111111111111111", b, c, {"fee": 3000}),
        arb.Edge("univ3", "0x1111111111111111111111111111111111111111", c, a, {"fee": 3000}),
    ]
    monkeypatch.setattr(arb, "build_edges", lambda *args, **kwargs: edges)

    clock = {"now": 0.0}
    monkeypatch.setattr(arb.time, "perf_counter", lambda: clock["now"])

    calls = {"count": 0}

    async def fake_quotes(rpc, cfg, cache, requested_edges, amount_in, metrics=None):
        calls["count"] += 1
        if calls["count"] == 1:
            # Simulate a slow first-leg quote phase without advancing the
            # post-quote route-evaluation clock.
            clock["now"] = 5.0
        if metrics is not None:
            metrics["quote_requests"] = int(metrics.get("quote_requests", 0)) + len(requested_edges)
            metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + len(requested_edges)
        result = {}
        for edge in requested_edges:
            if edge == edges[0]:
                amount_out = 110
            elif edge == edges[1]:
                amount_out = 110
            else:
                amount_out = 120
            result[arb.edge_key(edge)] = (amount_out, {"gas_estimate": 1, "fee": 3000})
        return result

    monkeypatch.setattr(arb, "quote_edges_batch", fake_quotes)
    monkeypatch.setattr(
        arb,
        "scan_efficiency_snapshot",
        lambda **kwargs: {
            "elapsed_ms": 0.0,
            "candidate_count": int(kwargs["candidate_count"]),
            "quote_requests": int(kwargs["quote_requests"]),
            "quote_successes": int(kwargs["quote_successes"]),
            "quote_success_rate": 1.0,
            "cache_hits": 0,
            "network_batches": 3,
        },
    )

    cfg = SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        safety=SimpleNamespace(slippage_bps=50),
    )

    telemetry = {}
    out = await arb.find_three_leg_opportunities(
        object(),
        cfg,
        object(),
        123,
        amount_in=100,
        slippage_bps=50,
        time_budget_ms=1,
        telemetry=telemetry,
    )

    assert len(out) >= 1
    assert any(item.expected_profit_raw == "20" for item in out)
    assert telemetry["route_groups_evaluated"] >= 1
    assert telemetry["budget_exhausted_after_quote"] is False


def test_three_leg_route_universe_exposes_pruned_edge_identity_and_pool():
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            name="ethereum",
            token_universe=["0x" + "11" * 20, "0x" + "22" * 20],
        )
    )
    edges = [
        arb.Edge(
            "univ3",
            "0x" + "aa" * 20,
            "0x" + "11" * 20,
            "0x" + f"{i + 2:040x}",
            {"fee": 3000, "pool": "0x" + f"{i + 100:040x}"},
        )
        for i in range(12)
    ]
    adjacency = {"0x" + "11" * 20: edges[:10]}
    pruned = edges[10:]
    snapshot = arb._route_universe_snapshot(
        cfg,
        edges,
        adjacency=adjacency,
        max_edges_per_token=10,
        pruned_edges=pruned,
    )

    assert snapshot["three_leg_edges_pruned_by_token_cap"] == 2
    assert len(snapshot["three_leg_pruned_edges"]) == 2
    assert snapshot["three_leg_pruned_edges"][0]["dex"] == "univ3"
    assert snapshot["three_leg_pruned_edges"][0]["token_in"] == "0x" + "11" * 20
    assert snapshot["three_leg_pruned_edges"][0]["token_out"] == "0x" + f"{12:040x}"
    assert snapshot["three_leg_pruned_edges"][0]["pool"] == "0x" + f"{110:040x}"
    assert snapshot["three_leg_pruned_edges"][0]["edge_id"].startswith("univ3:")
