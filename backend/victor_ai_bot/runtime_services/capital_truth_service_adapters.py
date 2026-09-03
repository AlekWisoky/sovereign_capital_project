from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


ReceiptSettlementBuilder = Callable[..., Dict[str, Any]]
PrimeLedgerReconciliationBuilder = Callable[..., Dict[str, Any]]
ConvergenceBuilder = Callable[..., Dict[str, Any]]


@dataclass(frozen=True)
class CapitalTruthServiceAdapterBundle:
    receipt_settlement_builder: ReceiptSettlementBuilder
    prime_ledger_reconciliation_builder: PrimeLedgerReconciliationBuilder
    convergence_builder: ConvergenceBuilder


def build_capital_truth_service_adapters(
    *,
    service: Any,
    runtime: Any,
) -> CapitalTruthServiceAdapterBundle:
    receipt_settlement = service._receipt_settlement_reconciliation
    prime_ledger_reconciliation = service._internal_prime_ledger_reconciliation
    capital_convergence = service._capital_convergence

    def receipt_settlement_builder(
        *, ledger_balances: Dict[str, Any], ledger_accounting: Dict[str, Any]
    ) -> Dict[str, Any]:
        return receipt_settlement(
            runtime,
            ledger_balances=ledger_balances,
            ledger_accounting=ledger_accounting,
        )

    def prime_ledger_reconciliation_builder(
        *,
        internal_prime_state: Dict[str, Any],
        account_balances: Dict[str, Any],
        accounting: Dict[str, Any],
    ) -> Dict[str, Any]:
        return prime_ledger_reconciliation(
            internal_prime_state=internal_prime_state,
            account_balances=account_balances,
            accounting=accounting,
        )

    def convergence_builder(**kwargs: Any) -> Dict[str, Any]:
        return capital_convergence(**kwargs)

    return CapitalTruthServiceAdapterBundle(
        receipt_settlement_builder=receipt_settlement_builder,
        prime_ledger_reconciliation_builder=prime_ledger_reconciliation_builder,
        convergence_builder=convergence_builder,
    )
