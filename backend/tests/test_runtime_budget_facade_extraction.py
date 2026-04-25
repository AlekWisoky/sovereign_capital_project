from types import SimpleNamespace

from victor_ai_bot.runtime_legacy import RuntimeBundle


class _ExecutionService:
    def __init__(self, amount: int):
        self.amount = amount
        self.calls = 0

    def resolve_amount_in(self, runtime):
        self.calls += 1
        return self.amount


def test_resolve_amount_in_delegates_to_execution_service() -> None:
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    service = _ExecutionService(150)
    bundle._execution_service = service

    assert bundle._resolve_amount_in() == 150
    assert service.calls == 1


def test_resolve_amount_in_returns_zero_without_execution_service() -> None:
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle._execution_service = None

    assert bundle._resolve_amount_in() == 0


def test_reset_budget_day_if_needed_rolls_budget_window() -> None:
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle._budget_day = "1970-01-01"
    bundle._gas_spent_today_wei = 123
    bundle._pending_gas_est_wei = 456

    bundle._reset_budget_day_if_needed()

    assert bundle._budget_day
    assert bundle._budget_day != "1970-01-01"
    assert bundle._gas_spent_today_wei == 0
    assert bundle._pending_gas_est_wei == 0


def test_gas_budget_remaining_wei_returns_large_sentinel_when_disabled() -> None:
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle.cfg = SimpleNamespace(execution=SimpleNamespace(daily_gas_budget_wei="0"))
    bundle._budget_day = "1970-01-01"
    bundle._gas_spent_today_wei = 999
    bundle._pending_gas_est_wei = 888

    assert bundle._gas_budget_remaining_wei() == 10**30


def test_gas_budget_remaining_wei_subtracts_spent_and_pending() -> None:
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle.cfg = SimpleNamespace(execution=SimpleNamespace(daily_gas_budget_wei="1000"))
    bundle._budget_day = __import__('time').strftime("%Y-%m-%d", __import__('time').gmtime())
    bundle._gas_spent_today_wei = 250
    bundle._pending_gas_est_wei = 100

    assert bundle._gas_budget_remaining_wei() == 650


def test_gas_budget_remaining_wei_treats_invalid_budget_as_disabled() -> None:
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle.cfg = SimpleNamespace(execution=SimpleNamespace(daily_gas_budget_wei="oops"))
    bundle._budget_day = __import__('time').strftime("%Y-%m-%d", __import__('time').gmtime())
    bundle._gas_spent_today_wei = 1
    bundle._pending_gas_est_wei = 2

    assert bundle._gas_budget_remaining_wei() == 10**30
