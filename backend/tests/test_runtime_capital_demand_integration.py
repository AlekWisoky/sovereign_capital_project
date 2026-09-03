from types import SimpleNamespace

from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


class _Decision:
    def __init__(self):
        self.kwargs = None

    def annotate_and_decide(self, opps, **kwargs):
        self.kwargs = kwargs
        return "decision"


class _Runtime(RuntimeDecisionFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(execution=SimpleNamespace())
        self._decision = _Decision()
        self._errors = []
        self.metrics = SimpleNamespace()
        self._capital = {
            "capital_engine": {
                "deployable_bankroll_wei": 10_000,
                "family_allocations_wei": {"prime_arb": 8_000},
            }
        }
        self._prime = {
            "stateReady": True,
            "capacityUsd": 1_000_000.0,
            "borrowedUsd": 500_000.0,
        }
        self._goal = {"state": {"aggressivenessCap": 0.75}}

    def capital_engine_state(self):
        return dict(self._capital)

    def internal_prime_state(self):
        return dict(self._prime)

    def wealth_goal_state(self):
        return dict(self._goal)


def test_safe_decide_opportunities_passes_composed_authority_to_decision_engine():
    rt = _Runtime()
    opp = SimpleNamespace(
        capital_required_usd=100.0,
        loan_source="internal_prime",
        strategy="",
        meta={"strategy_family": "prime_arb", "capital_source": "internal_prime"},
    )

    out = rt._safe_decide_opportunities(
        [opp],
        current_block=42,
        pending_txs=0,
        auto_enabled=True,
        gas_budget_remaining_wei=123,
    )

    assert out == "decision"
    assert rt._decision.kwargs["capital_budget_remaining_wei"] == 7_500
    assert rt._decision.kwargs["family_capital_remaining_wei"] == {"prime_arb": 3_000}
    assert rt._last_capital_demand is not None
    assert rt._last_capital_demand.prime_headroom_ratio == 0.5
