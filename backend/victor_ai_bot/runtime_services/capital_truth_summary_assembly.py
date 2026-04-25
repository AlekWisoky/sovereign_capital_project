from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from ..capital_family_policy import FAMILY_CAPITAL_PLAN_VERSION
from ..treasury.reconciliation import reconcile_internal_prime_journal
from .capital_truth_dependency_reads import (
    CapitalTruthDependencyReadBundle,
    build_capital_truth_dependency_reads,
)
from .capital_truth_derived_state import (
    CapitalTruthDerivedStateBundle,
    build_capital_truth_derived_state,
)
from .capital_truth_runtime_state_adapters import (
    CapitalTruthRuntimeStateAdapterBundle,
    build_capital_truth_runtime_state_adapters,
)
from .capital_truth_projection import build_capital_truth_projection
from .capital_truth_reconciliation import build_capital_truth_reconciliation_payload
from .capital_truth_source_snapshot import max_ts_ms


@dataclass(frozen=True)
class CapitalTruthSummaryAssemblyBundle:
    runtime_state: CapitalTruthRuntimeStateAdapterBundle
    derived: CapitalTruthDerivedStateBundle
    dependency_reads: CapitalTruthDependencyReadBundle
    receipt_settlement: Dict[str, Any]
    convergence: Dict[str, Any]
    reconciliation_payload: Dict[str, Any]
    truth: Dict[str, Any]


ReceiptSettlementBuilder = Callable[..., Dict[str, Any]]
PrimeLedgerReconciliationBuilder = Callable[..., Dict[str, Any]]
ConvergenceBuilder = Callable[..., Dict[str, Any]]


def build_capital_truth_summary_assembly(
    *,
    runtime: Any,
    now_ms: int,
    receipt_outcome_truth: Dict[str, Any],
    recovery_history: Dict[str, Any],
    receipt_settlement_builder: ReceiptSettlementBuilder,
    prime_ledger_reconciliation_builder: PrimeLedgerReconciliationBuilder,
    convergence_builder: ConvergenceBuilder,
) -> CapitalTruthSummaryAssemblyBundle:
    runtime_state = build_capital_truth_runtime_state_adapters(runtime)
    treasury_state = dict(runtime_state.treasury_state or {})
    capital_state = dict(runtime_state.capital_state or {})
    internal_prime_state = dict(runtime_state.internal_prime_state or {})
    launch = dict(runtime_state.launch_state or {})
    bankroll = runtime_state.bankroll
    bankroll_state = runtime_state.bankroll_state

    capital_engine = dict((capital_state or {}).get("capital_engine") or {})
    efficiency = dict((capital_state or {}).get("capital_efficiency_metrics") or {})
    reinvestment = dict((capital_state or {}).get("reinvestment_policy") or {})

    derived = build_capital_truth_derived_state(
        capital_engine=capital_engine,
        efficiency=efficiency,
        reinvestment=reinvestment,
        treasury_state=treasury_state,
        internal_prime_state=internal_prime_state,
        bankroll=bankroll,
        bankroll_state=bankroll_state,
    )
    dependency_reads = build_capital_truth_dependency_reads(runtime)
    receipt_settlement = receipt_settlement_builder(
        ledger_balances=dependency_reads.ledger_balances,
        ledger_accounting=dependency_reads.ledger_accounting,
    )
    ledger_ts_ms = max_ts_ms(
        [
            *[row.get("ts_ms") for row in dependency_reads.ledger_tail],
            *[row.get("ts_ms") for row in dependency_reads.ledger_transactions],
        ]
    )
    receipt_outcome_truth_degraded = bool(receipt_outcome_truth.get("is_degraded", False))
    receipt_outcome_truth_reason_code = str(
        receipt_outcome_truth.get("last_reason_code") or "settled_profit_truth_unavailable"
    )
    prime_journal_reconciliation = reconcile_internal_prime_journal(
        internal_prime_state,
        list(dependency_reads.ledger_transactions),
        strict=False,
    )
    prime_ledger_reconciliation = prime_ledger_reconciliation_builder(
        internal_prime_state=internal_prime_state,
        account_balances=dependency_reads.ledger_account_balances,
        accounting=dependency_reads.ledger_accounting,
    )
    convergence = convergence_builder(
        now_ms=now_ms,
        capital_state=capital_state,
        capital_engine=capital_engine,
        efficiency=efficiency,
        reinvestment=reinvestment,
        bankroll_state=bankroll_state,
        realized_profit_wei=int(derived.realized_profit_wei),
        deployed_capital_wei=int(derived.deployed_capital_wei),
        ledger_ts_ms=ledger_ts_ms,
        receipt_settlement=receipt_settlement,
        receipt_outcome_truth=receipt_outcome_truth,
        borrowed_usd=float(derived.borrowed_usd),
        prime_open_loan_count=int(derived.prime_open_loan_count),
        internal_prime_state=internal_prime_state,
        bankroll_history_event=dependency_reads.bankroll_history_event,
        treasury_history_snapshot=dependency_reads.treasury_history_snapshot,
        internal_prime_state_history_snapshot=dependency_reads.internal_prime_state_history_snapshot,
        bankroll_history_enabled=dependency_reads.bankroll_history_enabled,
        treasury_history_enabled=dependency_reads.treasury_history_enabled,
        internal_prime_history_enabled=dependency_reads.internal_prime_history_enabled,
        capital_event_enabled=dependency_reads.capital_event_enabled,
        capital_event_bankroll=dependency_reads.capital_event_bankroll,
        capital_event_treasury=dependency_reads.capital_event_treasury,
        capital_event_ledger=dependency_reads.capital_event_ledger,
        capital_event_receipt=dependency_reads.capital_event_receipt,
        capital_event_internal_prime=dependency_reads.capital_event_internal_prime,
    )

    chain_cfg = getattr(getattr(runtime, "cfg", None), "chain", None)
    execution_cfg = getattr(getattr(runtime, "cfg", None), "execution", None)
    launch_mode = str((launch.get("profile") or {}).get("mode") or "")
    reconciliation_payload = build_capital_truth_reconciliation_payload(
        treasury_balance_wei=int(derived.treasury_balance_wei),
        deployed_capital_wei=int(derived.deployed_capital_wei),
        withdrawable_balance_wei=int(derived.withdrawable_balance_wei),
        realized_profit_wei=int(derived.realized_profit_wei),
        prime_state_ready=bool(derived.prime_state_ready),
        prime_state_reason=str(derived.prime_state_reason),
        borrowed_usd=float(derived.borrowed_usd),
        prime_capacity_usd=float(derived.prime_capacity_usd),
        prime_utilization=float(derived.prime_utilization),
        prime_family_exposure=dict(derived.prime_family_exposure),
        prime_open_loan_count=int(derived.prime_open_loan_count),
        reserved_collateral_usd=float(derived.reserved_collateral_usd),
        collateralization_ratio=float(derived.collateralization_ratio),
        prime_journal_reconciliation=prime_journal_reconciliation,
        prime_ledger_reconciliation=prime_ledger_reconciliation,
        receipt_settlement=receipt_settlement,
        receipt_outcome_truth=receipt_outcome_truth,
        receipt_outcome_truth_degraded=receipt_outcome_truth_degraded,
        receipt_outcome_truth_reason_code=receipt_outcome_truth_reason_code,
        convergence=convergence,
        auto_reinvest=bool(derived.auto_reinvest),
        reinvest_rate_pct=float(derived.reinvest_rate_pct),
        launch_mode=launch_mode,
        capital_engine_present=bool(capital_engine),
        recovery_history=recovery_history,
        profit_destination=str(getattr(execution_cfg, "profit_to", "") or ""),
    )
    ledger = {
        "balances": dependency_reads.ledger_balances,
        "accountBalances": dependency_reads.ledger_account_balances,
        "accounting": dependency_reads.ledger_accounting,
        "tail": dependency_reads.ledger_tail[-10:],
        "transactions": dependency_reads.ledger_transactions[-10:],
        "last_ts_ms": int(ledger_ts_ms or 0),
    }
    truth = build_capital_truth_projection(
        now_ms=int(now_ms),
        status=str(reconciliation_payload.get("status") or "ok"),
        status_reason_code=str(reconciliation_payload.get("status_reason_code") or "ok"),
        reasons=list(reconciliation_payload.get("reasons") or []),
        chain=str(getattr(chain_cfg, "name", "") or ""),
        categories=dict(derived.categories),
        family_allocations=dict(derived.family_allocations),
        family_capital_plan_version=FAMILY_CAPITAL_PLAN_VERSION,
        family_capital_plan=list(derived.family_capital_plan),
        freshness=dict(reconciliation_payload.get("freshness") or {}),
        ledger=ledger,
        reconciliation=dict(reconciliation_payload.get("reconciliation") or {}),
        withdrawal=dict(reconciliation_payload.get("withdrawal") or {}),
    )
    return CapitalTruthSummaryAssemblyBundle(
        runtime_state=runtime_state,
        derived=derived,
        dependency_reads=dependency_reads,
        receipt_settlement=dict(receipt_settlement or {}),
        convergence=dict(convergence or {}),
        reconciliation_payload=dict(reconciliation_payload or {}),
        truth=dict(truth or {}),
    )
