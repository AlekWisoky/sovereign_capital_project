from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_primary_scan_facade as scan_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import RuntimePrimaryScanFacade

EXTRACTED_METHODS = {
    '_discover_extra_v3_pairs',
    '_scan_primary_opportunities',
}


class _Discovery:
    def __init__(self, pairs=None, venue_pools=None):
        self.pairs = list(pairs or [])
        self.venue_pools = dict(venue_pools or {})
        self.calls = []

    async def maybe_discover_univ3(self, rpc, cfg, block_number):
        self.calls.append({'rpc': rpc, 'cfg': cfg, 'block_number': block_number})
        return list(self.pairs)

    async def maybe_discover_venues(self, rpc, cfg, block_number):
        return dict(self.venue_pools)


class _Runtime(RuntimePrimaryScanFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            flags=SimpleNamespace(enable_two_leg_loops=True, enable_three_leg_loops=False, enable_v3_triangular=False),
            safety=SimpleNamespace(slippage_bps=75),
        )
        self.cache = object()
        self._discovery = _Discovery(
            ['v3-a', 'v3-b'],
            {'camelot_v2': [{
                'pool': 'pool-v2',
                'token_in': 'a',
                'token_out': 'b',
                'factory': 'factory-v2',
            }]},
        )


def _opp(profit: int, *, expected: int | None = None, amount_in: int | None = None):
    route = None
    if amount_in is not None:
        route = SimpleNamespace(legs=[SimpleNamespace(amount_in=str(amount_in))])
    return SimpleNamespace(
        id=f"opp-{profit}-{expected}",
        route_id=f"route-{profit}-{expected}",
        route=route,
        meta={'profit_after_gas_estimate_wei': profit} if profit >= 0 else {},
        expected_profit_raw=expected if expected is not None else max(0, profit),
    )


def test_runtime_bundle_inherits_primary_scan_facade():
    assert issubclass(RuntimeBundle, RuntimePrimaryScanFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_scan_primary_opportunities_preserves_discovery_scan_sort_and_truncate(monkeypatch):
    runtime = _Runtime()
    calls = {'two': None, 'three': None}

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        calls['two'] = {'rpc': rpc, 'cfg': cfg, 'cache': cache, 'block_number': block_number, **kwargs}
        kwargs['telemetry'].update({'quote_requests': 10, 'quote_successes': 8, 'routes_considered': 12, 'edges_generated': 6, 'quote_phase_ms': 100.0, 'route_evaluation_ms': 20.0, 'route_groups_evaluated': 2, 'budget_exhausted_after_quote': True})
        candidates = [_opp(5), _opp(20), _opp(-1, expected=11)]
        for candidate in candidates:
            candidate.meta["profitability"] = {
                "valid": True,
                "revalidated": True,
                "authoritative": True,
                "reason": "ok",
                "profit_after_costs_wei": str(
                    int(candidate.meta.get("profit_after_gas_estimate_wei") or candidate.expected_profit_raw)
                ),
                "flashloan_fee_wei": "1",
                "gas_cost_wei": "1",
            }
        return candidates

    async def fake_three(rpc, cfg, cache, block_number, **kwargs):
        calls['three'] = {'rpc': rpc, 'cfg': cfg, 'cache': cache, 'block_number': block_number, **kwargs}
        kwargs['telemetry'].update({'quote_requests': 4, 'quote_successes': 4, 'routes_considered': 5, 'edges_generated': 3, 'quote_phase_ms': 30.0, 'route_evaluation_ms': 7.5, 'route_groups_evaluated': 1, 'budget_exhausted_after_quote': False})
        candidate = _opp(15)
        candidate.meta["profitability"] = {
            "valid": True,
            "revalidated": True,
            "authoritative": True,
            "reason": "ok",
            "profit_after_costs_wei": "15",
            "flashloan_fee_wei": "1",
            "gas_cost_wei": "1",
        }
        return [candidate]

    monkeypatch.setattr(scan_mod, 'find_two_leg_opportunities', fake_two)
    monkeypatch.setattr(scan_mod, 'find_three_leg_opportunities', fake_three)
    runtime.cfg.flags.enable_three_leg_loops = True

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=10)

    assert runtime._discovery.calls[0]['block_number'] == 321
    assert calls['two']['amount_in'] == 10
    assert 0 < calls['two']['time_budget_ms'] <= 4000
    assert 0 < calls['three']['time_budget_ms'] <= 5000
    assert calls['two']['time_budget_ms'] + calls['three']['time_budget_ms'] <= 9000
    assert calls['two']['extra_v3_pairs'] == ['v3-a', 'v3-b']
    assert calls['three']['extra_v3_pairs'] == ['v3-a', 'v3-b']
    assert calls['three']['extra_camelot_v2_pools'] == [{
        'pool': 'pool-v2',
        'token_in': 'a',
        'token_out': 'b',
        'factory': 'factory-v2',
    }]
    assert runtime._market_pipeline_telemetry['quotes'] == {'requests': 14, 'successes': 12, 'failure_reasons': {}}
    assert runtime._market_pipeline_telemetry['routes_considered'] == 17
    assert runtime._market_pipeline_telemetry['edges_generated'] == 9
    assert runtime._market_pipeline_telemetry['route_evaluation'] == {'quote_phase_ms': 130.0, 'route_evaluation_ms': 27.5, 'route_groups_evaluated': 3, 'route_budget_exhausted': True, 'route_budget_stop_reason': 'time_budget', 'budget_exhausted_after_quote': True, 'two_leg_budget_ms': 4000, 'three_leg_budget_ms': 5000, 'configured_total_budget_ms': 9000}
    assert runtime._market_pipeline_telemetry['gross_candidates'] == 4
    adaptive = runtime._market_pipeline_telemetry['adaptive_size_discovery']
    assert adaptive['candidates_before_probe'] == 4
    assert adaptive['candidates_after_probe'] == 4
    assert adaptive['probe_candidate_delta'] == 0
    assert adaptive['probe_triggered'] is False
    assert adaptive['distinct_route_ids_before_probe'] == 4
    assert adaptive['distinct_route_ids_after_probe'] == 4
    assert [int((o.meta or {}).get('profit_after_gas_estimate_wei') or o.expected_profit_raw) for o in opps] == [20, 15, 11, 5]


@pytest.mark.asyncio
async def test_scan_primary_opportunities_returns_empty_when_amount_in_nonpositive(monkeypatch):
    runtime = _Runtime()

    async def unexpected(*args, **kwargs):
        raise AssertionError('scan should not run')

    monkeypatch.setattr(scan_mod, 'find_two_leg_opportunities', unexpected)
    monkeypatch.setattr(scan_mod, 'find_three_leg_opportunities', unexpected)

    opps = await runtime._scan_primary_opportunities(object(), current_block=1, amount_in=0)

    assert opps == []
    assert runtime._discovery.calls == []


@pytest.mark.asyncio
async def test_scan_primary_opportunities_does_not_swallow_unexpected_scan_bug(monkeypatch):
    runtime = _Runtime()

    async def boom(*args, **kwargs):
        raise KeyError('unexpected scan bug')

    monkeypatch.setattr(scan_mod, 'find_two_leg_opportunities', boom)

    with pytest.raises(KeyError, match='unexpected scan bug'):
        await runtime._scan_primary_opportunities(object(), current_block=7, amount_in=10)

    trace = runtime._market_pipeline_telemetry["scan_error_trace"]
    assert trace[-1]["function"] == "boom"
    assert trace[-1]["filename"] == "test_runtime_primary_scan_facade_extraction.py"
    assert trace[-1]["line"] > 0
    assert "unexpected scan bug" not in str(trace)



@pytest.mark.asyncio
async def test_scan_primary_opportunities_prefers_verified_after_cost_truth_over_gross_estimates(monkeypatch):
    runtime = _Runtime()

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        return [
            SimpleNamespace(
                id='gross-only',
                route_id='route-gross',
                meta={'profit_after_gas_estimate_wei': '500'},
                expected_profit_raw='900',
            ),
            SimpleNamespace(
                id='net-verified',
                route_id='route-net',
                meta={
                    'profit_after_gas_estimate_wei': '10',
                    'profit_after_costs': '250',
                    'safety': {'profit_after_costs_wei': '250'},
                },
                expected_profit_raw='100',
            ),
        ]

    async def fake_three(rpc, cfg, cache, block_number, **kwargs):
        return []

    monkeypatch.setattr(scan_mod, 'find_two_leg_opportunities', fake_two)
    monkeypatch.setattr(scan_mod, 'find_three_leg_opportunities', fake_three)

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=10)

    assert [getattr(o, 'id', '') for o in opps] == ['net-verified', 'gross-only']


@pytest.mark.asyncio
async def test_scan_enriches_canonical_after_fee_profit_with_explicit_usd(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.chain = SimpleNamespace(name="ethereum", usdc="0xusdc", usdt="")
    runtime.cfg.execution = SimpleNamespace(
        usd_accounting_enabled=True,
        usd_stable_preference="usdc",
        flashloan_fee_bps=0,
    )
    runtime.cfg.safety.minProfitAbs = 0
    runtime.cfg.safety.minProfitBps = 0
    opportunity = SimpleNamespace(
        id="canonical-usd",
        expected_profit_raw="100",
        expected_profit_usd="0",
        min_outs=["210"],
        route=SimpleNamespace(legs=[SimpleNamespace(token_in="0xtoken", amount_in="100")]),
        meta={"gas_cost_estimate_wei": "10"},
    )

    async def fake_usd(*args, **kwargs):
        assert kwargs["token"] == "0xtoken"
        assert kwargs["amount_wei"] == 100
        assert kwargs["block_number"] == 321
        return 5_000_000

    monkeypatch.setattr(scan_mod, "token_to_usd_micro", fake_usd)

    await runtime._annotate_canonical_after_fee_usd(
        opps=[opportunity],
        rpc=object(),
        current_block=321,
    )

    profitability = opportunity.meta["profitability"]
    assert profitability["authoritative"] is True
    assert profitability["profit_after_costs_wei"] == "100"
    assert profitability["profit_after_costs_usd_micro"] == 5_000_000
    assert opportunity.meta["safety"]["profit_after_costs_usd_micro"] == "5000000"
    assert opportunity.meta["canonical_after_fee_usd"]["source"] == "quote_derived_canonical_after_fee"


def test_adaptive_scan_amounts_returns_bounded_size_ladder(monkeypatch):
    runtime = _Runtime()

    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0,0.5,invalid")

    amounts = runtime._adaptive_scan_amounts(1000)

    assert amounts == [1000, 500, 2000, 4000, 8000, 16000]
    assert runtime._adaptive_size_min_opportunities == 2


def test_adaptive_scan_amounts_can_be_disabled(monkeypatch):
    runtime = _Runtime()

    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "0")

    assert runtime._adaptive_scan_amounts(1000) == [1000]


@pytest.mark.asyncio
async def test_scan_primary_opportunities_probes_alternative_sizes_when_base_has_too_few(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.flags.enable_three_leg_loops = False
    calls = []

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        calls.append(int(kwargs["amount_in"]))
        kwargs["telemetry"].update({
            "quote_requests": 1,
            "quote_successes": 1,
            "routes_considered": 1,
            "edges_generated": 1,
            "quote_phase_ms": 1.0,
            "route_evaluation_ms": 1.0,
            "route_groups_evaluated": 1,
        })
        amount = int(kwargs["amount_in"])
        return [
            _opp(amount - 10, expected=amount - 10, amount_in=amount),
        ]

    monkeypatch.setattr(scan_mod, "find_two_leg_opportunities", fake_two)
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0")

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=100)

    assert calls == [100, 50, 200, 400, 800, 1600]
    assert len(opps) == 6
    assert runtime._market_pipeline_telemetry["adaptive_size_discovery"]["amounts_scanned"] == ["100", "50", "200", "400", "800", "1600"]
    adaptive = runtime._market_pipeline_telemetry["adaptive_size_discovery"]
    assert adaptive["probe_triggered"] is True
    assert adaptive["candidates_before_probe"] == 1
    assert adaptive["candidates_after_probe"] == 6
    assert adaptive["probe_candidate_delta"] == 5
    assert adaptive["distinct_route_ids_before_probe"] == 1
    assert adaptive["distinct_route_ids_after_probe"] == 6
    assert [row["amount_in"] for row in adaptive["best_sizing_variants"]] == ["1600", "800", "400", "200", "100", "50"]


@pytest.mark.asyncio
async def test_scan_preserves_per_size_near_miss_economics_when_no_gross_candidates(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.flags.enable_three_leg_loops = False
    calls = []

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        amount = int(kwargs["amount_in"])
        calls.append(amount)
        kwargs["telemetry"].update({
            "quote_requests": 2,
            "quote_successes": 2,
            "routes_considered": 2,
            "edges_generated": 2,
            "route_groups_evaluated": 2,
            "size_economic_diagnostics": [{
                "route_id": f"route-{amount}",
                "amount_in": str(amount),
                "gross_profit_wei": str(-amount),
                "flashloan_fee_wei": str(amount * 9 // 10000),
                "gas_cost_wei": "100",
                "after_cost_profit_wei": str(-amount - (amount * 9 // 10000) - 100),
                "revalidated": False,
                "authoritative": False,
                "reason": "non_positive_gross_profit",
                "diagnostic_only": True,
            }],
        })
        return []

    monkeypatch.setattr(scan_mod, "find_two_leg_opportunities", fake_two)
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0")

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=100)

    assert opps == []
    assert calls == [100, 50, 200, 400, 800, 1600]
    evidence = runtime._market_pipeline_telemetry["size_economic_evidence"]
    assert [row["amount_in"] for row in evidence] == ["100", "50", "200", "400", "800", "1600"]
    assert all(row["diagnostic_only"] is True for row in evidence)
    assert runtime._market_pipeline_telemetry["adaptive_size_discovery"]["economic_matrix_complete"] is True



@pytest.mark.asyncio
async def test_scan_probes_when_gross_candidates_are_not_after_cost_profitable(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.flags.enable_three_leg_loops = False
    runtime.cfg.execution = SimpleNamespace(
        usd_accounting_enabled=False,
        flashloan_fee_bps=9,
    )
    runtime.cfg.safety.minProfitAbs = 0
    runtime.cfg.safety.minProfitBps = 0
    calls = []

    def sized_candidate(route_id: str, amount: int):
        return SimpleNamespace(
            id=f"{route_id}-{amount}",
            route_id=route_id,
            expected_profit_raw="100000",
            route=SimpleNamespace(
                legs=[SimpleNamespace(amount_in=str(amount), min_out=str(amount), token_in="0xtoken")]
            ),
            meta={
                "profitability": {
                    "valid": True,
                    "revalidated": True,
                    "authoritative": True,
                    "reason": "after_cost_non_positive",
                    "profit_after_costs_wei": "0",
                    "flashloan_fee_wei": "90",
                    "gas_cost_wei": "100000",
                }
            },
        )

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        amount = int(kwargs["amount_in"])
        calls.append(amount)
        kwargs["telemetry"].update({
            "quote_requests": 1,
            "quote_successes": 1,
            "routes_considered": 1,
            "edges_generated": 1,
            "route_groups_evaluated": 1,
        })
        if amount == 100:
            return [
                sized_candidate("route-a", amount),
                sized_candidate("route-b", amount),
            ]
        return []

    monkeypatch.setattr(scan_mod, "find_two_leg_opportunities", fake_two)
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0")

    opps = await runtime._scan_primary_opportunities(
        object(), current_block=321, amount_in=100
    )

    assert {int(o.route.legs[0].amount_in) for o in opps} == {100}
    assert calls == [100, 50, 200, 400, 800, 1600]
    adaptive = runtime._market_pipeline_telemetry["adaptive_size_discovery"]
    assert adaptive["candidates_before_probe"] == 2
    assert adaptive["authoritative_positive_candidates_before_probe"] == 0
    assert adaptive["probe_basis"] == "authoritative_after_cost_positive_count"
    assert adaptive["probe_triggered"] is True
    matrix = runtime._market_pipeline_telemetry["size_economic_matrix"]
    assert [row["amount_in"] for row in matrix] == ["100", "50", "200", "400", "800", "1600"]
    assert matrix[0]["quote_successes"] == 1
    assert matrix[0]["quote_failures"] == 0
    assert matrix[0]["candidates"][0]["route_id"] == "route-a"
    assert matrix[0]["candidates"][0]["after_cost_profit_wei"] == "0"
    assert matrix[0]["selection_basis"] == "economic_optimum_diagnostic"
    assert matrix[0]["economic_optimum_route_id"] == "route-a"
    assert matrix[0]["economic_optimum_after_cost_profit_wei"] == "0"
    assert all(row["selection_basis"] in {"economic_optimum_diagnostic", "no_economic_evidence", "verified_after_cost_profit"} for row in matrix)


def test_adaptive_scan_amounts_respects_borrow_cap(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.safety.max_borrow_amount = "1500"
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,1.5,2.0,4.0")

    assert runtime._adaptive_scan_amounts(1000) == [1000, 500, 1500, 1107, 1225, 1355]


def test_adaptive_scan_amounts_reaches_large_borrow_cap(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.safety.max_borrow_amount = "10000"
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,1.5,2.0,4.0")

    amounts = runtime._adaptive_scan_amounts(1000)

    assert amounts[0] == 1000
    assert 500 in amounts
    assert 1500 in amounts
    assert 4000 in amounts
    assert amounts[-1] == 10000
    assert len(amounts) <= 9


def test_adaptive_scan_amounts_uses_bounded_capless_discovery(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.safety.max_borrow_amount = "0"
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,1.5,2.0,4.0")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY_MAX_MULTIPLIER", "16")

    amounts = runtime._adaptive_scan_amounts(1000)

    assert amounts == [1000, 500, 1500, 2000, 4000, 8000, 16000]
    assert len(amounts) <= 9


@pytest.mark.asyncio
async def test_scan_selects_same_route_variant_by_verified_after_cost(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.flags.enable_three_leg_loops = False
    runtime.cfg.execution = SimpleNamespace(
        usd_accounting_enabled=False,
        flashloan_fee_bps=9,
    )
    runtime.cfg.safety.minProfitAbs = 0
    runtime.cfg.safety.minProfitBps = 0

    def sized_opp(amount: int, gross: int, net: int):
        return SimpleNamespace(
            id=f"opp-{amount}",
            route_id="same-route",
            expected_profit_raw=str(gross),
            route=SimpleNamespace(
                legs=[SimpleNamespace(amount_in=str(amount), min_out=str(amount + gross), token_in="0xtoken")]
            ),
            min_outs=[str(amount + gross)],
            meta={
                "gas_cost_estimate_wei": "10",
                "profitability": {
                    "revalidated": True,
                    "authoritative": True,
                    "valid": True,
                    "reason": "ok",
                    "profit_after_costs_wei": str(net),
                    "flashloan_fee_wei": str(amount * 9 // 10000),
                    "gas_cost_wei": "10",
                },
            },
        )

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        amount = int(kwargs["amount_in"])
        kwargs["telemetry"].update({
            "quote_requests": 1,
            "quote_successes": 1,
            "routes_considered": 1,
            "edges_generated": 1,
            "quote_phase_ms": 1.0,
            "route_evaluation_ms": 1.0,
            "route_groups_evaluated": 1,
        })
        if amount == 100:
            return [sized_opp(100, 150, 20)]
        if amount == 50:
            return [sized_opp(50, 80, 30)]
        return [sized_opp(amount, 220, 60)]

    monkeypatch.setattr(scan_mod, "find_two_leg_opportunities", fake_two)
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0")

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=100)

    assert len(opps) == 1
    assert int(opps[0].route.legs[0].amount_in) == 200
    assert runtime._market_pipeline_telemetry["size_economic_evidence"]
    assert runtime._market_pipeline_telemetry["adaptive_size_discovery"]["best_sizing_variants"][0]["amount_in"] == "200"



@pytest.mark.asyncio
async def test_scan_uses_revalidated_diagnostic_after_cost_for_economic_optimum(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.flags.enable_three_leg_loops = False
    runtime.cfg.execution = SimpleNamespace(
        usd_accounting_enabled=False,
        flashloan_fee_bps=9,
    )
    runtime.cfg.safety.minProfitAbs = 0
    runtime.cfg.safety.minProfitBps = 0

    def candidate(route_id: str, amount: int, gross: int, net: int):
        return SimpleNamespace(
            id=f"{route_id}-{amount}",
            route_id=route_id,
            expected_profit_raw=str(gross),
            route=SimpleNamespace(
                legs=[SimpleNamespace(amount_in=str(amount), min_out=str(amount + gross), token_in="0xtoken")]
            ),
            meta={
                "gas_cost_estimate_wei": str(510 if gross == 500 else 940),
                "profitability_diagnostic": {
                    "revalidated": True,
                    "authoritative": False,
                    "valid": False,
                    "reason": "after_cost_non_positive",
                    "gross_profit_wei": str(gross),
                    "profit_after_costs_wei": str(net),
                    "flashloan_fee_wei": "90",
                    "gas_cost_wei": str(510 if gross == 500 else 940),
                }
            },
        )

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        amount = int(kwargs["amount_in"])
        kwargs["telemetry"].update({
            "quote_requests": 2,
            "quote_successes": 2,
            "routes_considered": 2,
            "edges_generated": 2,
            "route_groups_evaluated": 2,
        })
        if amount == 100:
            # Gross ranking would choose route-b; true revalidated economics
            # must choose route-a because -10 > -40.
            return [
                candidate("route-a", amount, 500, -10),
                candidate("route-b", amount, 900, -40),
            ]
        return []

    monkeypatch.setattr(scan_mod, "find_two_leg_opportunities", fake_two)
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "0")

    opps = await runtime._scan_primary_opportunities(
        object(), current_block=321, amount_in=100
    )

    assert [getattr(o, "route_id", "") for o in opps] == ["route-a", "route-b"]
    matrix = runtime._market_pipeline_telemetry["size_economic_matrix"]
    assert matrix[0]["economic_optimum_route_id"] == "route-a"
    assert matrix[0]["economic_optimum_after_cost_profit_wei"] == "-10"
    rows = {row["route_id"]: row for row in matrix[0]["candidates"]}
    assert rows["route-a"]["after_cost_profit_wei"] == "-10"
    assert rows["route-a"]["revalidated"] is True
    assert rows["route-a"]["authoritative"] is False
    assert rows["route-a"]["reason"] == "profit_after_costs_not_positive"

@pytest.mark.asyncio
async def test_scan_revalidates_candidates_before_same_route_size_dedup(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.flags.enable_three_leg_loops = False
    runtime.cfg.execution = SimpleNamespace(usd_accounting_enabled=False)
    runtime.cfg.safety.minProfitAbs = 0
    runtime.cfg.safety.minProfitBps = 0

    def sized(amount: int, gross: int):
        return SimpleNamespace(
            id=f"opp-{amount}",
            route_id="same-route",
            expected_profit_raw=str(gross),
            route=SimpleNamespace(legs=[SimpleNamespace(amount_in=str(amount), token_in="0xtoken")]),
            meta={},
        )

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        amount = int(kwargs["amount_in"])
        kwargs["telemetry"].update({
            "quote_requests": 1,
            "quote_successes": 1,
            "routes_considered": 1,
            "edges_generated": 1,
            "route_groups_evaluated": 1,
        })
        if amount == 100:
            return [sized(100, 500)]
        if amount == 50:
            return [sized(50, 400)]
        return [sized(amount, 600)]

    def fake_revalidate(opportunity, cfg, *, stage, source, gas_cost_wei, quoted_amount_out_wei=None, gas_cost_in_profit_token_wei=None):
        amount = int(opportunity.route.legs[0].amount_in)
        return {
            "valid": True,
            "revalidated": True,
            "authoritative": True,
            "reason": "ok",
            "profit_after_costs_wei": str({50: 300, 100: 200, 200: 250}[amount]),
            "flashloan_fee_wei": str(amount // 10),
            "gas_cost_wei": "10",
        }

    monkeypatch.setattr(scan_mod, "find_two_leg_opportunities", fake_two)
    monkeypatch.setattr(scan_mod, "revalidate_profitability_state", fake_revalidate)
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0")

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=100)

    assert len(opps) == 1
    assert int(opps[0].route.legs[0].amount_in) == 50
    evidence = runtime._market_pipeline_telemetry["size_economic_evidence"]
    assert [row["amount_in"] for row in evidence] == ["100", "50", "200", "400", "800", "1600"]
    assert [row["after_cost_profit_wei"] for row in evidence] == ["200", "300", "250", "0", "0", "0"]
    assert [row["authoritative"] for row in evidence] == [True, True, True, False, False, False]


@pytest.mark.asyncio
async def test_invalid_revalidation_stays_diagnostic_only(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.flags.enable_three_leg_loops = False
    runtime.cfg.execution = SimpleNamespace(usd_accounting_enabled=False)

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        kwargs["telemetry"].update({"quote_requests": 1, "quote_successes": 1})
        return [
            SimpleNamespace(
                id="legacy",
                route_id="legacy-route",
                expected_profit_raw="900",
                route=None,
                meta={},
            )
        ]

    def fake_revalidate(opportunity, cfg, *, stage, source, gas_cost_wei, quoted_amount_out_wei=None, gas_cost_in_profit_token_wei=None):
        return {
            "valid": False,
            "revalidated": True,
            "authoritative": False,
            "reason": "missing_flashloan_fee",
            "profit_after_costs_wei": "0",
            "flashloan_fee_wei": "0",
            "gas_cost_wei": str(gas_cost_wei),
        }

    monkeypatch.setattr(scan_mod, "find_two_leg_opportunities", fake_two)
    monkeypatch.setattr(scan_mod, "revalidate_profitability_state", fake_revalidate)
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "0")

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=100)

    assert len(opps) == 1
    assert "profitability" not in opps[0].meta
    assert opps[0].meta["profitability_diagnostic"]["reason"] == "missing_flashloan_fee"
    assert runtime._market_pipeline_telemetry["size_economic_evidence"][0]["reason"] == "missing_flashloan_fee"
    assert runtime._market_pipeline_telemetry["size_economic_evidence"][0]["authoritative"] is False


@pytest.mark.asyncio
async def test_scan_preserves_sizing_telemetry_when_candidate_revalidation_fails(monkeypatch):
    runtime = _Runtime()
    runtime.cfg.flags.enable_three_leg_loops = False

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        amount = int(kwargs["amount_in"])
        kwargs["telemetry"].update({
            "quote_requests": 1,
            "quote_successes": 1,
            "routes_considered": 1,
            "edges_generated": 1,
            "route_groups_evaluated": 1,
        })
        return [
            SimpleNamespace(
                id=f"opp-{amount}",
                route_id=f"route-{amount}",
                expected_profit_raw="100",
                route=SimpleNamespace(
                    legs=[SimpleNamespace(amount_in=str(amount), token_in="0xtoken")]
                ),
                meta={"gas_cost_estimate_wei": "10"},
            )
        ]

    def failing_revalidate(*args, **kwargs):
        raise ValueError("bad candidate economics")

    monkeypatch.setattr(scan_mod, "find_two_leg_opportunities", fake_two)
    monkeypatch.setattr(scan_mod, "revalidate_profitability_state", failing_revalidate)
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")
    monkeypatch.setenv("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0")

    opps = await runtime._scan_primary_opportunities(
        object(), current_block=321, amount_in=100
    )

    assert len(opps) == 6
    assert {int(opp.route.legs[0].amount_in) for opp in opps} == {50, 100, 200, 400, 800, 1600}
    adaptive = runtime._market_pipeline_telemetry["adaptive_size_discovery"]
    assert adaptive["amounts_scanned"] == ["100", "50", "200", "400", "800", "1600"]
    assert adaptive["economic_matrix_complete"] is True
    evidence = runtime._market_pipeline_telemetry["size_economic_evidence"]
    assert len(evidence) == 6
    assert all(row["authoritative"] is False for row in evidence)
    assert all(row["reason"] == "revalidation_exception:ValueError" for row in evidence)
