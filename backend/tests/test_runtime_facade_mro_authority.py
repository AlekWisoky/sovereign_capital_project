from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_can_execute_facade import RuntimeCanExecuteFacade
from victor_ai_bot.runtime_services.runtime_state_facade import RuntimeStateFacade


# These assertions pin the concrete MRO owners so a facade placeholder cannot shadow them again.
def test_runtime_bundle_resolves_capital_engine_state_to_state_facade():
    assert RuntimeBundle.capital_engine_state is RuntimeStateFacade.capital_engine_state


def test_runtime_bundle_resolves_execution_readiness_to_can_execute_facade():
    assert RuntimeBundle._annotate_can_execute is RuntimeCanExecuteFacade._annotate_can_execute
