from dataclasses import dataclass

import pytest

from victor_ai_bot.capital_demand import CapitalDemandError, Money, selector_scalar
from test_capital_demand_contract import demand


@dataclass
class Composition:
    composed_before_decision: bool = False

    def compose(self, opportunity, *, final_size, treasury_state, provider_state):
        assert opportunity["id"] and final_size > 0
        assert treasury_state["denomination"] == "USDC"
        assert provider_state["capacity"] >= final_size
        self.composed_before_decision = True
        return demand(execution_notional=Money(final_size, "USDC", 6, "USDC"))


def test_demand_composition_requires_real_upstream_inputs_before_decision():
    composer = Composition()
    result = composer.compose({"id": "opp-1"}, final_size=1_000, treasury_state={"denomination": "USDC"}, provider_state={"capacity": 1_000})
    assert composer.composed_before_decision is True
    assert selector_scalar(result) == result.strategy_budget_consumption.amount


def test_missing_upstream_truth_fails_closed_instead_of_guessing():
    composer = Composition()
    with pytest.raises(AssertionError):
        composer.compose({"id": "opp-1"}, final_size=0, treasury_state={}, provider_state={})
