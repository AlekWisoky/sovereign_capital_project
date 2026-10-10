from __future__ import annotations

from types import SimpleNamespace

import victor_ai_bot.arb_engine as arb


def test_three_leg_frontier_uses_best_quote_within_same_directed_pair():
    token_in = "0x" + "11" * 20
    token_out = "0x" + "22" * 20
    low = arb.Edge(
        "univ3", "0x" + "aa" * 20, token_in, token_out,
        {"fee": 3000, "pool": "pool-low"},
    )
    high = arb.Edge(
        "univ3", "0x" + "aa" * 20, token_in, token_out,
        {"fee": 500, "pool": "pool-high"},
    )
    selected, _ = arb._select_three_leg_frontier_edges(
        [(0, low), (1, high)],
        active_protocols_by_token={token_in: {"univ3"}},
        active_pools_by_token={token_in: {"univ3:pool:pool-existing"}},
        active_routers_by_token={token_in: {"0x" + "aa" * 20}},
        per_token_cap=1,
        global_cap=1,
        quoted_output_by_edge={
            arb.edge_key(low): 100,
            arb.edge_key(high): 110,
        },
    )
    assert selected == [high]


def test_three_leg_route_sort_prefers_signed_after_cost_net_over_gross():
    gross_winner = SimpleNamespace(
        route_id="gross-winner",
        expected_profit_raw="1000000",
        meta={"profitability": {"profit_after_costs_wei": "-900000", "revalidated": True}},
    )
    net_winner = SimpleNamespace(
        route_id="net-winner",
        expected_profit_raw="200000",
        meta={"profitability": {
            "profit_after_costs_wei": "100000",
            "revalidated": True,
            "authoritative": False,
        }},
    )
    assert arb._opportunity_economic_sort_key(net_winner) > arb._opportunity_economic_sort_key(gross_winner)


def test_three_leg_route_sort_compares_after_cost_usd_across_borrow_tokens():
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    high_raw_wei_low_usd = SimpleNamespace(
        route_id="raw-wei-winner",
        expected_profit_raw="100000000000000000000",
        route=SimpleNamespace(legs=[SimpleNamespace(token_in=token_a)]),
        meta={
            "profitability": {"profit_after_costs_wei": "100000000000000000000"},
            "canonical_after_fee_usd": {"profit_after_costs_usd_micro": "100"},
        },
    )
    low_raw_wei_high_usd = SimpleNamespace(
        route_id="usd-winner",
        expected_profit_raw="1000",
        route=SimpleNamespace(legs=[SimpleNamespace(token_in=token_b)]),
        meta={
            "profitability": {"profit_after_costs_wei": "1000"},
            "canonical_after_fee_usd": {"profit_after_costs_usd_micro": "200"},
        },
    )
    assert arb._opportunity_economic_sort_key(low_raw_wei_high_usd) > arb._opportunity_economic_sort_key(high_raw_wei_low_usd)
