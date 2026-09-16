from types import SimpleNamespace

from victor_ai_bot.aqe.mev.search_engine import MEVSearchEngine


ADDRESS_ROUTER = "0x" + "1" * 40
TOKEN_IN = "0x" + "2" * 40
TOKEN_OUT = "0x" + "3" * 40
PROFIT_TO = "0x" + "4" * 40
TX_HASH = "0x" + "a" * 64


def _word(value: int) -> str:
    return f"{value:064x}"


def _address_word(address: str) -> str:
    return _word(int(address[2:], 16))


def _exact_input_single() -> str:
    return "0x414bf389" + "".join(
        [
            _address_word(TOKEN_IN),
            _address_word(TOKEN_OUT),
            _word(3000),
            _address_word(PROFIT_TO),
            _word(1_900_000_000),
            _word(1_000_000),
            _word(900_000),
            _word(0),
        ]
    )


def _base_opportunity():
    return SimpleNamespace(
        id="opp-flash-1",
        route_id="route-flash-1",
        strategy="flash_arb",
        expected_profit_raw=50_000,
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(
                    dex="univ3",
                    venue=ADDRESS_ROUTER,
                    token_in=TOKEN_IN,
                    token_out=TOKEN_OUT,
                    amount_in=1_000_000,
                    min_out=900_000,
                    data="0x01",
                ),
                SimpleNamespace(
                    dex="curve",
                    venue=PROFIT_TO,
                    token_in=TOKEN_OUT,
                    token_out=TOKEN_IN,
                    amount_in=900_000,
                    min_out=850_000,
                    data="0x02",
                ),
            ]
        ),
    )


def _evidence():
    return {
        "simulation_id": "sim-router-1",
        "deterministic": True,
        "fork_block": 123,
        "pre_state_root": "0xpre",
        "post_state_root": "0xpost",
        "scenario_digest": "sha256:router-1",
        "scenario_results": [
            {
                "gas_multiplier": 1.0,
                "liquidity_multiplier": 1.0,
                "oracle_multiplier": 1.0,
                "conflict_checked": True,
                "reverted": False,
            }
        ],
        "reverted": False,
        "economics": {
            "simulation_id": "sim-router-1",
            "scenario_digest": "sha256:router-1",
            "expected_realized_profit_usd": 17.5,
            "gross_asset_delta_usd": 20.0,
            "gas_cost_usd": 2.0,
            "borrow_cost_usd": 0.5,
        },
    }


def test_pending_router_call_is_wired_into_existing_mev_producer_boundary():
    tx = {
        "hash": TX_HASH,
        "to": ADDRESS_ROUTER,
        "input": _exact_input_single(),
        "value_wei": 0,
        "tags": ["dex_like"],
        "sel": "0x414bf389",
        "simulation_request": {
            "fork_url": "https://example.invalid/rpc",
            "fork_block": 123,
            "transaction": {"hash": TX_HASH, "to": ADDRESS_ROUTER, "data": _exact_input_single()},
            "scenarios": [
                {
                    "gas_multiplier": 1.0,
                    "liquidity_multiplier": 1.0,
                    "oracle_multiplier": 1.0,
                    "economic_observation": {
                        "account": PROFIT_TO,
                        "assets": [
                            {"address": "native", "decimals": 18, "price_usd": 2000.0, "role": "profit"}
                        ],
                    },
                }
            ],
        },
    }

    class _Executor:
        def simulate(self, **request):
            assert request["transaction"]["hash"] == TX_HASH
            return _evidence()

    engine = MEVSearchEngine(
        fork_executor=_Executor(),
        router=ADDRESS_ROUTER,
        provider="aave",
        profit_to=PROFIT_TO,
    )
    rows = engine.search(
        mev_state={"sample_pending": [tx], "high_risk_ratio": 0.0},
        base_opportunities=[_base_opportunity()],
    )

    assert len(rows) == 1
    assert rows[0].expected_profit_usd == 17.5
    assert rows[0].metadata["economics_status"] == "simulation_backed"
    assert rows[0].metadata["flash_arb_context"]["source_opportunity_id"] == "opp-flash-1"
    assert rows[0].lifecycle_eligibility == "observe_only"
    assert rows[0].policy_eligibility == "observe_only"


def test_arbitrary_pending_transaction_without_explicit_simulation_context_cannot_be_promoted():
    tx = {
        "hash": TX_HASH,
        "to": ADDRESS_ROUTER,
        "input": _exact_input_single(),
        "value_wei": 0,
        "tags": ["dex_like"],
        "sel": "0x414bf389",
    }
    engine = MEVSearchEngine(
        router=ADDRESS_ROUTER,
        provider="aave",
        profit_to=PROFIT_TO,
    )
    rows = engine.search(
        mev_state={"sample_pending": [tx], "high_risk_ratio": 0.0},
        base_opportunities=[_base_opportunity()],
    )

    assert len(rows) == 1
    assert rows[0].expected_profit_usd == 0.0
    assert "flash_arb_context" not in rows[0].metadata
    assert rows[0].lifecycle_eligibility == "observe_only"
    assert rows[0].policy_eligibility == "observe_only"
