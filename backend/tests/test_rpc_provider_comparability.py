from __future__ import annotations

from typing import Any

from victor_ai_bot.rpc_economic_selector import RpcEconomicEvidence
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    _provider_results_are_comparable,
)


def _provider_row(endpoint: str, options: dict[str, Any] | None = None):
    options = dict(options or {})
    block = int(options.get("block", 123))
    amount_ladder = tuple(options.get("amount_ladder", ("1000",)))
    gas_price = str(options.get("gas_price", "100"))
    fee_bps = str(options.get("fee_bps", "5"))
    healthy = bool(options.get("healthy", True))
    scan_error = str(options.get("scan_error", ""))
    telemetry = {
        "route_universe": {
            "configured_token_count": 4,
            "active_token_count": 7,
            "edges_by_dex": {"univ3": 12, "aerodrome": 4},
            "unique_directed_pairs": 10,
        },
        "adaptive_size_discovery": {"amounts_scanned": list(amount_ladder)},
        "scan_sizing": {"amounts_by_token": {"0xtoken": "1000"}},
        "provider_comparison_cost_inputs": {
            "block_number": block,
            "base_amount_in": "1000",
            "gas_price_wei": gas_price,
            "gas_price_status": "consensus",
            "flashloan_fee_bps": fee_bps,
            "flashloan_fee_ok": True,
            "flashloan_fee_status": "ok",
        },
        "scan_error": scan_error,
    }
    evidence = RpcEconomicEvidence(
        endpoint=endpoint,
        provider=endpoint.rsplit("/", 1)[-1],
        profit_after_costs_usd_micro=0,
        profitable_opportunity_count=0,
        quote_requests=10,
        quote_successes=9,
        block_number=block,
        healthy=healthy,
    )
    return endpoint, [], None, telemetry, evidence


def test_provider_economics_requires_matching_block_graph_size_and_costs():
    a = _provider_row("https://rpc-a.example")
    b = _provider_row("https://rpc-b.example")

    assert _provider_results_are_comparable([a, b], 123) == (
        True,
        "matched_graph_block_sizes_and_cost_inputs",
    )

    wrong_size = _provider_row(
        "https://rpc-b.example", {"amount_ladder": ("1000", "2000")}
    )
    assert _provider_results_are_comparable([a, wrong_size], 123) == (
        False,
        "provider_graph_size_or_cost_inputs_mismatch",
    )

    wrong_cost = _provider_row("https://rpc-b.example", {"gas_price": "101"})
    assert _provider_results_are_comparable([a, wrong_cost], 123) == (
        False,
        "provider_graph_size_or_cost_inputs_mismatch",
    )


def test_provider_economics_fails_closed_for_unusable_costs_or_incomplete_race():
    a = _provider_row("https://rpc-a.example")
    unavailable = _provider_row("https://rpc-b.example", {"gas_price": ""})
    assert _provider_results_are_comparable([a, unavailable], 123) == (
        False,
        "shared_provider_cost_inputs_unavailable",
    )

    failed = _provider_row(
        "https://rpc-b.example",
        {"healthy": False, "scan_error": "provider_scan_timeout"},
    )
    assert _provider_results_are_comparable([a, failed], 123) == (
        False,
        "fewer_than_two_healthy_completed_provider_results",
    )

    different_block = _provider_row("https://rpc-b.example", {"block": 124})
    assert _provider_results_are_comparable([a, different_block], 123) == (
        False,
        "fewer_than_two_healthy_completed_provider_results",
    )
