from dataclasses import replace

import pytest

from victor_ai_bot.capital_demand import CapitalDemandError, Money, selector_scalar
from test_capital_demand_contract import NOW, demand


def test_composition_contract_requires_final_inputs_before_selection():
    value = demand()
    assert value.provenance.source_event == "opp-1"
    assert selector_scalar(value, now=NOW) == value.strategy_budget_consumption.amount


def test_size_borrow_requote_capacity_and_gas_changes_invalidate_old_demand():
    value = demand()
    changed_size = replace(value, execution_notional=Money(11_000_000, "USDC", 6, "USDC"))
    assert changed_size.validate(now=NOW) is not value.validate(now=NOW)
    changed_provider = replace(value, provider_capacity_requirement=replace(value.provider_capacity_requirement, amount=10_000_000))
    assert changed_provider.validate(now=NOW) is not value.validate(now=NOW)
    changed_gas = replace(value, gas_reserve=Money(0, "USD", 2, "USD"))
    assert changed_gas.validate(now=NOW).value == "invalid"


def test_missing_or_ambiguous_upstream_truth_fails_closed():
    with pytest.raises(CapitalDemandError):
        demand(source_identity="")
