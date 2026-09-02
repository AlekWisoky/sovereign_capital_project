from types import SimpleNamespace

from victor_ai_bot.omar.lifecycle_bridge import capital_authority_context, ensure_lineage


def test_capital_authority_context_reads_capital_engine_state_only():
    runtime = SimpleNamespace(
        capital_engine_state=lambda: {
            "capital_engine": {
                "available_bankroll_wei": 900,
                "deployable_bankroll_wei": 600,
                "family_allocations_wei": {"ARBITRAGE": 400, "MEV": 200},
                "status": "healthy",
                "freshness_class": "fresh",
                "authority_id": "prime-authority-1",
                "source": "internal_prime",
                "internal_prime_available": True,
                "prime_capacity_ratio": 0.75,
                "prime_cost_bps": 4.0,
            }
        }
    )

    context = capital_authority_context(runtime)

    assert context["capital_authority_source"] == "capital_engine_state"
    assert context["capital_available_wei"] == 900
    assert context["capital_allocatable_wei"] == 600
    assert context["capital_family_allocations_wei"] == {"ARBITRAGE": 400, "MEV": 200}
    assert context["internal_prime_available"] is True
    assert context["prime_capacity_ratio"] == 0.75
    assert context["prime_cost_bps"] == 4.0


def test_lineage_is_persisted_on_decision_and_opportunity():
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={"brain": {"omar_decision_id": "decision-1"}})
    decision = SimpleNamespace(metadata={})

    decision_id, correlation_id = ensure_lineage(opp, decision, 123)

    assert decision_id == "decision-1"
    assert correlation_id.startswith("corr_")
    assert opp.meta["brain"]["canonical_decision_id"] == decision_id
    assert opp.meta["brain"]["correlation_id"] == correlation_id
    assert decision.metadata["canonical_decision_id"] == decision_id
    assert decision.metadata["correlation_id"] == correlation_id
