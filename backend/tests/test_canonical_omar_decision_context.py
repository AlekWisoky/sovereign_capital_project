from types import SimpleNamespace

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.runtime_services import runtime_decision_facade as decision_module
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


def test_decision_boundary_carries_capital_authority_into_omar(monkeypatch, tmp_path):
    monkeypatch.setattr(
        decision_module,
        "build_features",
        lambda opp: SimpleNamespace(margin_ratio=0.001, gas_ratio=0.0003, legs=2),
    )
    monkeypatch.setattr(decision_module, "opportunity_route_ready", lambda opp: (True, "", []))
    monkeypatch.setattr(
        decision_module,
        "inspect_profit_after_costs_truth",
        lambda opp: SimpleNamespace(verified=True, positive=True),
    )
    omar = OmarRuntime(OmarConfig(enabled=True, real_learning_enabled=True, real_learning_min_observations=1), chain_name="ethereum")
    omar.learning_path = str(tmp_path / "omar.json")
    omar._real_learner.path = omar.learning_path

    runtime = object.__new__(RuntimeDecisionFacade)
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._omar = omar
    runtime._wealth_goal_service = None
    runtime._market_regime = {"volatility": 0.1}
    opp = SimpleNamespace(id="opp-context", route_id="route-context", meta={"brain": {"p_success": 0.9, "ev_wei": 100}})
    decision = SimpleNamespace(metadata={})

    runtime.capital_engine_state = lambda: {"capital_engine": {"status": "authorized", "freshness_class": "fresh", "available_bankroll_wei": 1000, "deployable_bankroll_wei": 800}}
    chosen, selected = runtime._apply_omar_to_candidate(opp, decision, current_block=123)

    assert chosen is opp
    assert selected is decision
    assert opp.meta["brain"]["canonical_decision_id"]
    assert not opp.meta["brain"]["canonical_decision_id"].startswith("omar-")
    pending = omar._pending_decisions[opp.meta["brain"]["canonical_decision_id"]]
    context = pending["context"]
    assert context["capital_authority_source"] == "capital_engine_state"
    assert context["capital_authority_status"] == "authorized"
    assert context["capital_authority_freshness"] == "fresh"
