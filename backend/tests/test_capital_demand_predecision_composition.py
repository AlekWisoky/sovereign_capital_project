from dataclasses import replace

from victor_ai_bot.capital_demand import Money, matches_execution_plan, selector_scalar
from test_capital_demand_contract import NOW, demand


def test_composition_contract_requires_final_inputs_before_selection():
    value = demand()
    assert value.provenance.source_event == "opp-1"
    assert selector_scalar(value, now=NOW) == value.strategy_budget_consumption.amount


def test_size_borrow_requote_capacity_and_gas_changes_cannot_reuse_old_demand():
    value = demand()
    changed_size = Money(11_000_000, "USDC", 6, "USDC")
    assert not matches_execution_plan(value, execution_plan_id="plan-2", execution_notional=changed_size, now=NOW)
    changed_provider = replace(value, provider_capacity_requirement=replace(value.provider_capacity_requirement, amount=10_000_000))
    assert changed_provider.validate(now=NOW).value == "invalid"
    changed_gas = replace(value, gas_reserve=Money(0, "USD", 2, "USD"))
    assert changed_gas.validate(now=NOW).value == "invalid"


def test_matching_final_plan_is_explicitly_valid():
    value = demand()
    assert matches_execution_plan(value, execution_plan_id="plan-1", execution_notional=value.execution_notional, now=NOW)
