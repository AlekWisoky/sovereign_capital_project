from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.capital_truth_runtime_state_adapters import (
    build_capital_truth_runtime_state_adapters,
)
from victor_ai_bot.runtime_services.capital_truth_summary_assembly import (
    build_capital_truth_summary_assembly,
)
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from tests.test_capital_truth_summary_assembly_kernel_maintenance import _Runtime


class _PartialBankrollState:
    realized_profit_wei = 0


class _PartialBankroll:
    state = _PartialBankrollState()


class _PartialTreasuryRepo:
    def latest(self, *, state_type: str):
        assert state_type == "capital_snapshot"
        return {"payload": {"treasuryBalanceWei": 11}}


class _PartialPrime:
    def snapshot(self):
        return {"stateReady": False}


class _PartialRuntime:
    _bankroll = _PartialBankroll()
    _treasury = SimpleNamespace(_state_repo=_PartialTreasuryRepo())
    _internal_prime = _PartialPrime()
    _capital_engine_state = {"capital_engine": {"deployable_bankroll_wei": 22}}

    def treasury_state(self):
        raise AssertionError("canonical truth must not call the treasury facade")

    def capital_engine_state(self):
        raise AssertionError("canonical truth must not call the capital facade")

    def internal_prime_state(self):
        raise AssertionError("canonical truth must not call the prime facade")

    def launch_state(self):
        return {"profile": {"mode": "TEST"}}



def test_capital_truth_runtime_state_adapter_kernel_reads_materialized_state_without_runtime_facades() -> None:
    bundle = build_capital_truth_runtime_state_adapters(_PartialRuntime())

    assert bundle.treasury_state["treasuryBalanceWei"] == 11
    assert bundle.capital_state["capital_engine"]["deployable_bankroll_wei"] == 22
    assert bundle.internal_prime_state["stateReady"] is False
    assert bundle.launch_state["profile"]["mode"] == "TEST"
    assert bundle.bankroll is _PartialRuntime._bankroll
    assert bundle.bankroll_state is _PartialRuntime._bankroll.state



def test_capital_truth_summary_assembly_uses_runtime_state_adapter_kernel() -> None:
    service = CapitalTruthService()
    runtime = _Runtime()
    bundle = build_capital_truth_summary_assembly(
        runtime=runtime,
        now_ms=1_700_000_000_500,
        receipt_outcome_truth={},
        recovery_history={"component": "capital_truth", "degraded_count": 0},
        receipt_settlement_builder=(
            lambda *, ledger_balances, ledger_accounting: service._receipt_settlement_reconciliation(
                runtime,
                ledger_balances=ledger_balances,
                ledger_accounting=ledger_accounting,
            )
        ),
        prime_ledger_reconciliation_builder=(
            lambda *, internal_prime_state, account_balances, accounting: service._internal_prime_ledger_reconciliation(
                internal_prime_state=internal_prime_state,
                account_balances=account_balances,
                accounting=accounting,
            )
        ),
        convergence_builder=(lambda **kwargs: service._capital_convergence(**kwargs)),
    )

    assert bundle.runtime_state.launch_state["profile"]["mode"] == "V1_PLUS_STABLE_ALPHA"
    assert bundle.runtime_state.capital_state["capital_engine"]["deployable_bankroll_wei"] == 25 * 10**18
    assert bundle.truth["canonical"] is True
