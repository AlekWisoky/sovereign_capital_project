"""Characterization of the missing authoritative pre-decision CapitalDemand seam.

This is specification evidence, not a production composer and not a closed-loop,
live-execution, settlement, recovery, or replay proof.
"""

from __future__ import annotations

import inspect

from victor_ai_bot.decision_engine import DecisionEngine


def test_predecision_capital_demand_composer_is_required_before_selection():
    """Fail until production composes and validates CapitalDemand before selection."""
    required = {
        "route_amount": "production provenance",
        "strategy_family": "production provenance",
        "profitability": "economic truth",
        "execution_plan_id": "execution identity",
        "correlation_id": "lineage",
        "treasury_capacity": "aggregate budget truth",
        "execution_notional": "separate from treasury commitment",
        "internal_capital_commitment": "separate dimension",
        "gas_reserve": "separate dimension",
        "fee_reserve": "separate dimension",
        "provider_capacity": "separate dimension",
        "worst_case_exposure": "separate dimension",
        "strategy_budget_consumption": "selector scalar",
        "asset": "identity",
        "decimals": "identity",
        "denomination": "explicit treasury denomination",
        "conversion_evidence": "cross-denomination authority",
        "freshness": "stale data fails closed",
        "provenance": "structured source evidence",
        "wealth_goal": "modifier, never authorizer",
        "aggressiveness": "bounded modifier, never bypass",
        "phase_a": "flash_arb only when ready and governed",
        "strategy_modes": "single/multi/ai-managed controls",
        "correlation_crowding_capacity": "portfolio constraints",
        "latency_freshness": "economic admission constraint",
    }
    assert required["strategy_budget_consumption"] == "selector scalar"
    assert required["execution_notional"] != required["internal_capital_commitment"]

    source = inspect.getsource(DecisionEngine.annotate_and_decide)
    assert "CapitalDemand" in source, (
        "MISSING PRODUCTION SEAM: DecisionEngine reaches portfolio selection "
        "without an authoritative pre-decision CapitalDemand composer. "
        "Implement the additive composer before changing selector/runtime behavior."
    )
