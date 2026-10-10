from __future__ import annotations

from victor_ai_bot.gas_adjusted_split_router import (
    _normalize_candidate,
    _prepare_candidate_buckets,
    build_gas_adjusted_split_frontier,
)


TOKEN_A = "0x" + "11" * 20
TOKEN_X = "0x" + "22" * 20
TOKEN_Y = "0x" + "33" * 20
TOKEN_Z = "0x" + "44" * 20
ROUTER = "0x" + "55" * 20
FEE_AUX = "0x" + (3000).to_bytes(32, "big").hex()
SECOND_FEE_AUX = "0x" + (500).to_bytes(32, "big").hex()


def _legs(
    middle: str,
    amount: int = 5_000_000,
    *,
    first_aux: str = FEE_AUX,
    second_aux: str = SECOND_FEE_AUX,
):
    return [
        {
            "dex": "univ3",
            "venue": ROUTER,
            "token_in": TOKEN_A,
            "token_out": middle,
            "amount_in": str(amount),
            "min_out": str(amount + 500),
            "data": first_aux,
        },
        {
            "dex": "univ3",
            "venue": ROUTER,
            "token_in": middle,
            "token_out": TOKEN_A,
            "amount_in": str(amount + 500),
            "min_out": str(amount + 800),
            "data": second_aux,
        },
    ]


def _candidate(route_id: str, economics: tuple[int, int], legs):
    amount, gross = economics
    gas_token = "700000"
    return {
        "route_id": route_id,
        "amount_in": str(amount),
        "gross_profit_wei": str(gross),
        "amount_out_wei": str(amount + gross),
        "flashloan_fee_wei": str(max(1, amount // 1000)),
        "gas_cost_profit_token_wei": gas_token,
        "gas_cost_conversion_available": gas_token not in ("", None),
        "gas_cost_wei": "40000000",
        "gas_cost_l2_wei": "40000000",
        "gas_units_estimate": "400000",
        "base_l1_fee_wei": "0",
        "base_l1_fee_status": "not_applicable",
        "legs": legs,
        "repayment_valid": True,
        "revalidated": False,
        "authoritative": False,
        "valid": False,
        "diagnostic_only": True,
    }


def _matrix(*rows):
    return [
        {
            "amount_in": str(amount),
            "quote_requests": 10,
            "quote_successes": 10,
            "candidates": candidates,
        }
        for amount, candidates in rows
    ]


def test_gas_adjusted_split_frontier_finds_better_partition_but_never_grants_authority():
    route_c = _candidate(
        "route-c", (10_000_000, 1_500_000), _legs(TOKEN_Z, 10_000_000)
    )
    route_c["gas_cost_profit_token_wei"] = "1600000"
    matrix = _matrix(
        (5_000_000, [
            _candidate("route-a", (5_000_000, 1_000_000), _legs(TOKEN_X)),
            _candidate("route-b", (5_000_000, 1_000_000), _legs(TOKEN_Y)),
        ]),
        (10_000_000, [route_c]),
    )

    result = build_gas_adjusted_split_frontier(matrix, chain_id=1)

    assert result["enabled"] is True
    assert result["execution_supported"] is False
    assert result["execution_authority_granted"] is False
    assert result["positive_after_cost_estimates"] >= 1
    plan = next(
        row for row in result["plans"]
        if row["amount_in"] == "10000000" and row["route_count"] == 2
    )
    assert set(plan["route_ids"]) == {"route-a", "route-b"}
    assert int(plan["economic_after_cost_profit_wei"]) > 0
    assert plan["better_than_best_single_estimate"] is True
    assert plan["required_executor_abi_version"] == 3
    assert plan["simulation_required_before_authority"] is True
    assert plan["revalidated"] is False
    assert plan["authoritative"] is False
    assert plan["identity_coverage"]["unique_protocols"] == 1
    assert plan["identity_coverage"]["unique_pool_keys"] == 4
    assert plan["identity_coverage"]["unique_router_ids"] == 1
    assert plan["identity_coverage"]["unique_directed_pairs"] == 4
    assert plan["identity_coverage"]["router_identity_is_not_a_profit_score"] is True


def test_candidate_shortlist_keeps_near_best_pool_diversity_not_raw_router_count():
    matrix = _matrix(
        (5_000_000, [
            _candidate("best-net", (5_000_000, 1_000_000), _legs(TOKEN_X)),
            _candidate("near-net-diverse-pool", (5_000_000, 998_600), _legs(TOKEN_Y)),
            _candidate("economically-distant", (5_000_000, 900_000), _legs(TOKEN_Z)),
        ])
    )
    buckets = _prepare_candidate_buckets(
        matrix,
        chain_id=1,
        max_per_amount=2,
    )
    selected = {row["route_id"] for row in buckets[TOKEN_A]}
    assert selected == {"best-net", "near-net-diverse-pool"}
    assert "economically-distant" not in selected


def test_split_optimizer_rejects_reuse_of_same_pool_across_routes():
    shared_route_b = [
        {
            "dex": "univ3",
            "venue": ROUTER,
            "token_in": TOKEN_A,
            "token_out": TOKEN_X,
            "amount_in": "5000000",
            "min_out": "5000500",
            "data": FEE_AUX,
        },
        {
            "dex": "univ3",
            "venue": ROUTER,
            "token_in": TOKEN_X,
            "token_out": TOKEN_A,
            "amount_in": "5000500",
            "min_out": "5000800",
            "data": "0x" + (10000).to_bytes(32, "big").hex(),
        },
    ]
    result = build_gas_adjusted_split_frontier(
        _matrix(
            (5_000_000, [
                _candidate("route-a", (5_000_000, 1_000_000), _legs(TOKEN_X)),
                _candidate("route-b-shared-pool", (5_000_000, 1_000_000), shared_route_b),
            ]),
            (10_000_000, [
                _candidate("route-c", (10_000_000, 2_000_000), _legs(TOKEN_Z, 10_000_000)),
            ]),
        ),
        chain_id=1,
    )
    assert not any(row["route_count"] >= 2 for row in result["plans"])


def test_split_optimizer_rejects_native_gas_cost_unit_mismatch():
    candidate = _candidate(
        "gas-mismatch",
        (5_000_000, 1_000_000),
        _legs(TOKEN_X),
    )
    candidate["gas_cost_wei"] = "39999999"
    candidate["gas_cost_l2_wei"] = "40000000"
    candidate["base_l1_fee_wei"] = "0"
    assert _normalize_candidate(candidate, chain_id=1) is None


def test_component_must_repay_principal_and_flash_fee():
    candidate = _candidate(
        "not-repayable",
        (5_000_000, 1_000_000),
        _legs(TOKEN_X),
    )
    candidate["repayment_valid"] = False
    assert _normalize_candidate(candidate, chain_id=1) is None


def test_curve_coin_index_directions_do_not_create_distinct_pool_identities():
    pool = "0x" + "66" * 20
    curve_roundtrip = [
        {
            "dex": "curve",
            "venue": pool,
            "token_in": TOKEN_A,
            "token_out": TOKEN_X,
            "amount_in": "5000000",
            "min_out": "5000500",
            "data": "0x" + (1 << 8).to_bytes(32, "big").hex(),
        },
        {
            "dex": "curve",
            "venue": pool,
            "token_in": TOKEN_X,
            "token_out": TOKEN_A,
            "amount_in": "5000500",
            "min_out": "5000800",
            "data": "0x" + (1).to_bytes(32, "big").hex(),
        },
    ]
    candidate = _candidate(
        "curve-same-pool-roundtrip",
        (5_000_000, 1_000_000),
        curve_roundtrip,
    )
    assert _normalize_candidate(candidate, chain_id=1) is None


def test_split_optimizer_fails_closed_when_gas_conversion_is_missing():
    route_a = _candidate("route-a", (5_000_000, 1_000_000), _legs(TOKEN_X))
    route_b = _candidate("route-b", (5_000_000, 1_000_000), _legs(TOKEN_Y))
    route_a["gas_cost_profit_token_wei"] = ""
    route_b["gas_cost_profit_token_wei"] = ""
    result = build_gas_adjusted_split_frontier(
        _matrix((5_000_000, [route_a, route_b])),
        chain_id=1,
    )
    assert result["eligible_route_amount_evidence"] == 0
    assert result["plans"] == []
    assert result["reason_code"] == "no_routes_with_complete_positive_gross_and_gas_cost_evidence"


def test_base_split_optimizer_requires_exact_l1_fee_evidence():
    result = build_gas_adjusted_split_frontier(
        _matrix((5_000_000, [
            _candidate("route-a", (5_000_000, 1_000_000), _legs(TOKEN_X)),
            _candidate("route-b", (5_000_000, 1_000_000), _legs(TOKEN_Y)),
        ])),
        chain_id=8453,
    )
    assert result["eligible_route_amount_evidence"] == 0
    assert result["plans"] == []
