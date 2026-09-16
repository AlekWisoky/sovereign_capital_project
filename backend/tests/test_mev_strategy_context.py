from victor_ai_bot.aqe.mev.search_engine import MEVSearchEngine
from victor_ai_bot.aqe.mev.strategy_context import MEVStrategySimulationContextProducer


def _address(n: int) -> str:
    return f"0x{n:040x}"


def _context(tx_hash: str):
    address = _address(1)
    return {
        "strategy": "flash_arb",
        "tx_hash": tx_hash,
        "provider": "aave",
        "borrow_token": address,
        "profit_to": address,
        "amount_borrow": 1_000_000,
        "expected_profit_raw": 50_000,
        "legs": [
            {
                "dex": "univ3",
                "venue": _address(2),
                "token_in": address,
                "token_out": _address(3),
                "amount_in": 1_000_000,
                "min_out": 1_000_001,
                "data": "0x01",
            }
        ],
        "simulation_request": {
            "fork_url": "https://example.invalid/rpc",
            "fork_block": 123,
            "transaction": {"hash": tx_hash, "to": _address(2), "data": "0xabcdef12"},
            "scenarios": [
                {
                    "gas_multiplier": 1.0,
                    "liquidity_multiplier": 1.0,
                    "oracle_multiplier": 1.0,
                    "economic_observation": {
                        "account": _address(4),
                        "assets": [{"address": "native", "decimals": 18, "price_usd": 2000.0, "role": "profit"}],
                    },
                }
            ],
        },
    }


def test_strategy_context_producer_requires_explicit_economic_observation():
    producer = MEVStrategySimulationContextProducer()
    tx_hash = "0x" + "1" * 64
    context = _context(tx_hash)
    assert producer.produce(tx_hash=tx_hash, strategy_context=context) is not None

    missing = _context(tx_hash)
    missing["simulation_request"]["scenarios"][0].pop("economic_observation")
    assert producer.produce(tx_hash=tx_hash, strategy_context=missing) is None


def test_strategy_context_producer_rejects_mismatched_pending_transaction():
    producer = MEVStrategySimulationContextProducer()
    context = _context("0x" + "1" * 64)
    assert producer.produce(tx_hash="0x" + "2" * 64, strategy_context=context) is None


def test_mev_search_consumes_produced_context_without_inventing_it():
    tx_hash = "0x" + "3" * 64
    context = _context(tx_hash)
    evidence = {
        "simulation_id": "sim-1",
        "deterministic": True,
        "fork_block": 123,
        "pre_state_root": "0xpre",
        "post_state_root": "0xpost",
        "scenario_digest": "sha256:scenario-1",
        "scenario_results": [{
            "gas_multiplier": 1.0,
            "liquidity_multiplier": 1.0,
            "oracle_multiplier": 1.0,
            "conflict_checked": True,
            "reverted": False,
        }],
        "reverted": False,
        "economics": {
            "simulation_id": "sim-1",
            "scenario_digest": "sha256:scenario-1",
            "expected_realized_profit_usd": 17.5,
            "gross_asset_delta_usd": 20.0,
            "gas_cost_usd": 2.0,
            "borrow_cost_usd": 0.5,
        },
    }

    class _Executor:
        def simulate(self, **request):
            assert request["transaction"]["hash"] == tx_hash
            assert request["scenarios"][0]["economic_observation"]["assets"]
            return evidence

    rows = MEVSearchEngine(fork_executor=_Executor()).search(
        mev_state={
            "sample_pending": [{
                "hash": tx_hash,
                "to": _address(2),
                "value_wei": 0,
                "tags": ["dex_like"],
                "sel": "0xabcdef12",
                "strategy_context": context,
            }],
            "high_risk_ratio": 0.0,
        },
        base_opportunities=[],
        chain="ethereum",
        chain_id=1,
        regime="balanced",
    )
    assert len(rows) == 1
    assert rows[0].expected_profit_usd == 17.5
    assert rows[0].metadata["economics_status"] == "simulation_backed"
    assert rows[0].metadata["flash_arb_context"]["strategy"] == "flash_arb"


def test_heuristic_pending_transaction_stays_non_authoritative_without_context():
    rows = MEVSearchEngine().search(
        mev_state={
            "sample_pending": [{
                "hash": "0x4",
                "to": _address(2),
                "value_wei": 5 * 10**18,
                "tags": ["dex_like"],
                "sel": "0xabcdef12",
            }],
            "high_risk_ratio": 0.2,
        },
        base_opportunities=[],
    )
    assert rows[0].expected_profit_usd == 0.0
    assert rows[0].metadata["economics_status"] == "heuristic_non_authoritative"
