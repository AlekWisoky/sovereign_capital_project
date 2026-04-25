from __future__ import annotations

from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.runtime_services.capital_truth_service_adapters import (
    build_capital_truth_service_adapters,
)


class _Runtime:
    pass


class _TrackingService:
    def __init__(self) -> None:
        self.calls = []

    def _receipt_settlement_reconciliation(self, runtime, *, ledger_balances, ledger_accounting):
        self.calls.append(("receipt", runtime, ledger_balances, ledger_accounting))
        return {"ok": True, "kind": "receipt"}

    def _internal_prime_ledger_reconciliation(self, *, internal_prime_state, account_balances, accounting):
        self.calls.append(("prime", internal_prime_state, account_balances, accounting))
        return {"ok": True, "kind": "prime"}

    def _capital_convergence(self, **kwargs):
        self.calls.append(("convergence", kwargs))
        return {"ok": True, "kind": "convergence"}



def test_capital_truth_service_adapter_kernel_bridges_remaining_service_callbacks() -> None:
    runtime = _Runtime()
    service = _TrackingService()
    bundle = build_capital_truth_service_adapters(service=service, runtime=runtime)

    receipt = bundle.receipt_settlement_builder(
        ledger_balances={"USDC": 1.0},
        ledger_accounting={"assetAccounts": {}},
    )
    prime = bundle.prime_ledger_reconciliation_builder(
        internal_prime_state={"borrowedUsd": 10.0},
        account_balances={"internal_prime:borrowed_usd": {"USD": 10.0}},
        accounting={"encumberedAssets": {}},
    )
    convergence = bundle.convergence_builder(now_ms=123, capital_state={})

    assert receipt["kind"] == "receipt"
    assert prime["kind"] == "prime"
    assert convergence["kind"] == "convergence"
    assert service.calls[0][0] == "receipt"
    assert service.calls[0][1] is runtime
    assert service.calls[1][0] == "prime"
    assert service.calls[2][0] == "convergence"



def test_capital_truth_service_summary_still_emits_canonical_projection_through_service_adapter_kernel(monkeypatch) -> None:
    from tests.test_capital_truth_summary_assembly_kernel_maintenance import _Runtime as SummaryRuntime

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.capital_truth_service_shell.time.time",
        lambda: 1_700_000_000.5,
    )

    truth = CapitalTruthService().summary(SummaryRuntime())

    assert truth["canonical"] is True
    assert truth["read_model"] == "ledgered_capital_truth_v3_converged"
    assert truth["summaryContract"]["readModel"] == "capital_truth_projection_v1"
