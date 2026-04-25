from __future__ import annotations

import json
import os
import time
import uuid
from copy import deepcopy
from typing import Any, Dict

from ..domain_errors import (
    BorrowLimitError,
    CapitalAllocationError,
    CollateralInsufficiencyError,
    LedgerConsistencyError,
)
from ..outcomes import CapitalDecision
from .borrow_costs import internal_borrow_cost
from .contracts import PrimeBorrowRequest, PrimeLoanPosition
from .inventory import InventoryPool
from ..pathing import canonical_data_dir
from ..persistence.db import PersistenceDB
from ..persistence.repositories.ledger_repository import LedgerRepository
from ..persistence.repositories.capital_event_repository import CapitalEventRepository
from ..persistence.repositories.internal_prime_state_repository import InternalPrimeStateRepository
from ..treasury.ledger import LedgerLine, LedgerTransaction, TreasuryLedger


class InternalPrimeAllocator:
    def __init__(
        self,
        *,
        data_dir: str = "backend/data",
        chain: str = "default",
        db: PersistenceDB | None = None,
        capital_event_repo: CapitalEventRepository | None = None,
        capital_write_service: Any | None = None,
    ):
        self.data_dir = canonical_data_dir(data_dir or "backend/data")
        self.chain = str(chain or "default")
        state_dir = os.path.join(self.data_dir, "internal_prime")
        os.makedirs(state_dir, exist_ok=True)
        self.inventory = InventoryPool(path=os.path.join(state_dir, f"inventory_{self.chain}.json"))
        self._state_path = os.path.join(state_dir, f"state_{self.chain}.json")
        self._ledger = TreasuryLedger(data_dir=self.data_dir, chain=self.chain)
        self._db = None
        self._capital_event_repo = capital_event_repo
        self._capital_write_service = capital_write_service
        self._ledger_repo = None
        self._state_repo = None
        self._state_updated_ts_ms = int(time.time() * 1000)
        try:
            self._db = db or PersistenceDB(
                os.path.join(self.data_dir, "state", "xdv_runtime_state.sqlite3")
            )
            if self._capital_event_repo is None:
                self._capital_event_repo = CapitalEventRepository(self._db, chain=self.chain)
            self._ledger_repo = LedgerRepository(
                self._db,
                capital_event_repo=self._capital_event_repo,
                chain=self.chain,
            )
            self._state_repo = InternalPrimeStateRepository(self._db, chain=self.chain)
        except (OSError, RuntimeError, TypeError, ValueError):
            self._db = None
            self._ledger_repo = None
            self._state_repo = None
        self._utilization = 0.0
        self._borrowed_usd = 0.0
        self._capacity_usd = 10_000_000.0
        self._family_exposure: Dict[str, float] = {}
        self._loans: Dict[str, Dict[str, Any]] = {}
        self._state_ready = True
        self._state_status = "ok"
        self._state_reason_code = ""
        self._state_reason = ""
        self._load_state()
        self._ensure_state_history_bootstrap()

    def _mark_state_unavailable(self, *, reason_code: str, reason: str | None = None) -> None:
        self._state_ready = False
        self._state_status = "unavailable"
        self._state_reason_code = str(reason_code or "prime_state_unavailable")
        self._state_reason = str(reason or self._state_reason_code)

    def _clear_state_unavailable(self) -> None:
        self._state_ready = True
        self._state_status = "ok"
        self._state_reason_code = ""
        self._state_reason = ""

    def _load_state(self) -> None:
        payload: Dict[str, Any] = {}
        file_error_reason = ""
        if os.path.exists(self._state_path):
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    payload = dict(json.load(f) or {})
            except OSError:
                payload = {}
                file_error_reason = "prime_state_unavailable"
                self._mark_state_unavailable(reason_code=file_error_reason)
            except (ValueError, TypeError):
                payload = {}
                file_error_reason = "prime_state_corrupt"
                self._mark_state_unavailable(reason_code=file_error_reason)
        if not payload:
            repo_payload = self._load_state_from_repo()
            if repo_payload:
                payload = repo_payload
        if not payload:
            if file_error_reason:
                return
            self._clear_state_unavailable()
            return
        try:
            self._borrowed_usd = float(payload.get("borrowedUsd") or 0.0)
            self._capacity_usd = max(1.0, float(payload.get("capacityUsd") or 10_000_000.0))
            self._family_exposure = {
                str(k): float(v) for k, v in dict(payload.get("familyExposure") or {}).items()
            }
            self._loans = {str(k): dict(v) for k, v in dict(payload.get("loans") or {}).items()}
            self._state_updated_ts_ms = int(
                payload.get("updatedTsMs")
                or payload.get("updated_ts_ms")
                or int(time.time() * 1000)
            )
            inventory_payload = dict(payload.get("inventory") or {})
            if inventory_payload:
                self.inventory._assets = {str(k): float(v) for k, v in inventory_payload.items()}
            self._recompute_utilization()
            self._clear_state_unavailable()
        except (ValueError, TypeError):
            self._utilization = 0.0
            self._borrowed_usd = 0.0
            self._capacity_usd = 10_000_000.0
            self._family_exposure = {}
            self._loans = {}
            self._state_updated_ts_ms = int(time.time() * 1000)
            self._mark_state_unavailable(reason_code="prime_state_corrupt")

    def _raw_state_payload(self) -> Dict[str, Any]:
        return {
            "utilization": round(self._utilization, 8),
            "borrowedUsd": round(self._borrowed_usd, 8),
            "capacityUsd": round(self._capacity_usd, 8),
            "familyExposure": {k: round(v, 8) for k, v in self._family_exposure.items()},
            "loans": deepcopy(self._loans),
            "inventory": self.inventory.snapshot(),
            "updatedTsMs": int(self._state_updated_ts_ms or int(time.time() * 1000)),
            "stateReady": bool(self._state_ready),
            "stateStatus": str(
                self._state_status or ("ok" if self._state_ready else "unavailable")
            ),
            "stateReasonCode": str(
                self._state_reason_code or ("" if self._state_ready else "prime_state_unavailable")
            ),
            "stateReason": str(
                self._state_reason
                or self._state_reason_code
                or ("" if self._state_ready else "prime_state_unavailable")
            ),
        }

    def _state_snapshot_payload_from_raw(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw = dict(payload or {})
        loans = {str(k): dict(v) for k, v in dict(raw.get("loans") or {}).items()}
        open_loans = [
            dict(v) for v in loans.values() if str((v or {}).get("status") or "") == "open"
        ]
        disputed_loans = [
            dict(v) for v in loans.values() if str((v or {}).get("status") or "") == "disputed"
        ]
        active_loans = [*open_loans, *disputed_loans]
        borrowed_usd = round(float(raw.get("borrowedUsd") or 0.0), 2)
        reserved_collateral_usd = round(
            sum(
                float(
                    (loan or {}).get("collateral_reserved_usd")
                    or (loan or {}).get("notional_usd")
                    or 0.0
                )
                for loan in active_loans
            ),
            8,
        )
        collateralization_ratio = round(
            (
                reserved_collateral_usd / max(1.0, float(raw.get("borrowedUsd") or 0.0))
                if float(raw.get("borrowedUsd") or 0.0) > 0.0
                else 0.0
            ),
            8,
        )
        return {
            "borrowedUsd": borrowed_usd,
            "capacityUsd": round(float(raw.get("capacityUsd") or 10_000_000.0), 2),
            "utilization": round(float(raw.get("utilization") or 0.0), 6),
            "updatedTsMs": int(raw.get("updatedTsMs") or raw.get("updated_ts_ms") or 0),
            "inventory": {
                str(k): round(float(v), 8) for k, v in dict(raw.get("inventory") or {}).items()
            },
            "familyExposure": {
                str(k): round(float(v), 2) for k, v in dict(raw.get("familyExposure") or {}).items()
            },
            "loans": loans,
            "openLoans": open_loans,
            "disputedLoans": disputed_loans,
            "loanCount": int(len(active_loans)),
            "disputedLoanCount": int(len(disputed_loans)),
            "reservedCollateralUsd": reserved_collateral_usd,
            "collateralizationRatio": collateralization_ratio,
            "stateReady": bool(raw.get("stateReady", self._state_ready)),
            "stateStatus": str(
                raw.get("stateStatus")
                or ("ok" if bool(raw.get("stateReady", self._state_ready)) else "unavailable")
            ),
            "stateReasonCode": str(
                raw.get("stateReasonCode")
                or (
                    ""
                    if bool(raw.get("stateReady", self._state_ready))
                    else "prime_state_unavailable"
                )
            ),
            "stateReason": str(
                raw.get("stateReason")
                or raw.get("stateReasonCode")
                or (
                    ""
                    if bool(raw.get("stateReady", self._state_ready))
                    else "prime_state_unavailable"
                )
            ),
        }

    def _load_state_from_repo(self) -> Dict[str, Any]:
        repo = self._state_repo
        if repo is None or not hasattr(repo, "latest"):
            return {}
        try:
            latest = repo.latest(state_type="prime_state")
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            latest = {}
        payload = dict(latest.get("payload") or {}) if isinstance(latest, dict) else {}
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _save_state(self) -> None:
        payload = self._raw_state_payload()
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        self._clear_state_unavailable()

    def _record_state_snapshot(
        self,
        payload: Dict[str, Any],
        *,
        state_type: str = "prime_state",
        conn: Any | None = None,
        transaction_id: str = "",
        receipt_id: str = "",
        source: str = "internal_prime_allocator",
    ) -> None:
        snapshot_payload = self._state_snapshot_payload_from_raw(dict(payload or {}))
        ts_ms = int(
            snapshot_payload.get("updatedTsMs")
            or snapshot_payload.get("updated_ts_ms")
            or int(time.time() * 1000)
        )
        if self._state_repo is not None and hasattr(self._state_repo, "append_snapshot"):
            self._state_repo.append_snapshot(
                ts_ms=ts_ms,
                state_type=str(state_type or "prime_state"),
                payload=snapshot_payload,
                conn=conn,
            )
        if self._capital_event_repo is not None and hasattr(
            self._capital_event_repo, "append_event"
        ):
            self._capital_event_repo.append_event(
                ts_ms=ts_ms,
                domain="internal_prime",
                event_type=str(state_type or "prime_state"),
                source=str(source or "internal_prime_allocator"),
                transaction_id=str(transaction_id or ""),
                receipt_id=str(receipt_id or ""),
                entity_id="internal_prime_state",
                payload=snapshot_payload,
                conn=conn,
            )

    def _ensure_state_history_bootstrap(self) -> None:
        if self._state_repo is None or not hasattr(self._state_repo, "latest"):
            return
        try:
            latest = self._state_repo.latest(state_type="prime_state")
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            latest = {}
        latest_payload = dict(latest.get("payload") or {}) if isinstance(latest, dict) else {}
        state_payload = self._raw_state_payload()
        if latest_payload and latest_payload == state_payload:
            return
        try:
            self._record_state_snapshot(state_payload, state_type="prime_state_bootstrap")
        except (OSError, RuntimeError, TypeError, ValueError):
            return

    def adopt_state_payload(self, payload: Dict[str, Any], *, persist_mirror: bool = True) -> None:
        state_payload = dict(payload or {})
        self._borrowed_usd = float(state_payload.get("borrowedUsd") or 0.0)
        self._capacity_usd = max(1.0, float(state_payload.get("capacityUsd") or 10_000_000.0))
        self._family_exposure = {
            str(k): float(v) for k, v in dict(state_payload.get("familyExposure") or {}).items()
        }
        self._loans = {str(k): dict(v) for k, v in dict(state_payload.get("loans") or {}).items()}
        self._state_updated_ts_ms = int(
            state_payload.get("updatedTsMs")
            or state_payload.get("updated_ts_ms")
            or int(time.time() * 1000)
        )
        self._state_ready = bool(state_payload.get("stateReady", True))
        self._state_status = str(
            state_payload.get("stateStatus") or ("ok" if self._state_ready else "unavailable")
        )
        self._state_reason_code = str(
            state_payload.get("stateReasonCode")
            or ("" if self._state_ready else "prime_state_unavailable")
        )
        self._state_reason = str(state_payload.get("stateReason") or self._state_reason_code)
        inventory_payload = dict(state_payload.get("inventory") or {})
        self.inventory._assets = {str(k): float(v) for k, v in inventory_payload.items()}
        self._recompute_utilization(capacity_usd=self._capacity_usd)
        if persist_mirror:
            self._save_state()
            try:
                self.inventory._save()
            except (OSError, RuntimeError, TypeError, ValueError):
                pass

    def _prime_journal_lines(self, *, loan: Dict[str, Any], opened: bool) -> list[LedgerLine]:
        notional = float(loan.get("notional_usd") or 0.0)
        collateral_reserved = float(loan.get("collateral_reserved_usd") or notional)
        family = str(loan.get("family") or "")
        asset = str(loan.get("asset") or "USD")
        note = "prime_loan_open" if opened else "prime_loan_settlement"
        delta = round(collateral_reserved - notional, 8)
        lines = [
            LedgerLine(
                account="internal_prime:borrowed_usd",
                asset="USD",
                amount=(notional if opened else -notional),
                family=family,
                note=note,
            ),
            LedgerLine(
                account=f"internal_prime:inventory_reserved:{asset}",
                asset=asset,
                amount=(-collateral_reserved if opened else collateral_reserved),
                family=family,
                note=note,
            ),
        ]
        if abs(delta) > 1e-9:
            lines.append(
                LedgerLine(
                    account="internal_prime:collateral_buffer",
                    asset="",
                    amount=(delta if opened else -delta),
                    family=family,
                    note=note,
                )
            )
        return lines

    def _rollback_release_reserved_inventory(self, asset: str, amount: float) -> tuple[bool, str]:
        try:
            self.inventory.release(asset, amount)
            return True, ""
        except (OSError, RuntimeError, TypeError, ValueError, CollateralInsufficiencyError):
            self._mark_state_unavailable(reason_code="prime_inventory_rollback_failed")
            return False, "prime_inventory_rollback_failed"

    def _rollback_reserve_released_inventory(self, asset: str, amount: float) -> tuple[bool, str]:
        try:
            self.inventory.reserve(asset, amount, strict=True)
            return True, ""
        except (OSError, RuntimeError, TypeError, ValueError, CollateralInsufficiencyError):
            self._mark_state_unavailable(reason_code="prime_settlement_inventory_rollback_failed")
            return False, "prime_settlement_inventory_rollback_failed"

    def _write_ledger_transaction(self, tx: Any) -> Dict[str, Any]:
        repo = getattr(self, "_ledger_repo", None)
        if repo is not None:
            repo.append_transaction(chain=self.chain, payload=tx.to_dict())
        try:
            self._ledger.write_transaction(tx)
        except (OSError, RuntimeError, TypeError, ValueError, LedgerConsistencyError):
            if repo is not None and hasattr(repo, "delete_transaction"):
                try:
                    repo.delete_transaction(chain=self.chain, transaction_id=tx.transaction_id)
                except (OSError, RuntimeError, TypeError, ValueError):
                    pass
            raise
        return tx.to_dict()

    @staticmethod
    def _tx_dict_to_transaction(payload: Dict[str, Any]) -> LedgerTransaction:
        tx_payload = dict(payload or {})
        return LedgerTransaction(
            transaction_id=str(tx_payload.get("transaction_id") or ""),
            ts_ms=int(tx_payload.get("ts_ms") or 0),
            tx_type=str(tx_payload.get("tx_type") or ""),
            chain=str(tx_payload.get("chain") or ""),
            receipt_id=str(tx_payload.get("receipt_id") or ""),
            lines=[LedgerLine(**dict(line)) for line in list(tx_payload.get("lines") or [])],
            metadata=dict(tx_payload.get("metadata") or {}),
        )

    def _prime_decision_audit_lines(self, *, family: str, reason_code: str) -> list[LedgerLine]:
        note = f"prime_loan_rejected:{str(reason_code or 'prime_allocation_denied')}"
        return [
            LedgerLine(
                account="internal_prime:decision_audit",
                asset="",
                amount=0.0,
                family=family,
                note=note,
            ),
            LedgerLine(account="equity:offset", asset="", amount=0.0, family=family, note=note),
        ]

    def _record_prime_decision_event(
        self,
        *,
        event: str,
        request: PrimeBorrowRequest,
        decision: CapitalDecision,
    ) -> Dict[str, Any]:
        decision_details = (
            dict(decision.details or {}) if isinstance(decision.details, dict) else {}
        )
        tx = self._ledger.build_transaction(
            tx_type=str(event),
            chain=self.chain,
            receipt_id="",
            lines=self._prime_decision_audit_lines(
                family=str(request.family or ""),
                reason_code=str(decision.reason_code or "prime_allocation_denied"),
            ),
            metadata={
                "requestId": str(request.request_id or ""),
                "family": str(request.family or ""),
                "asset": str(request.asset or ""),
                "capitalSource": str(request.capital_source or ""),
                "notionalUsd": float(request.notional_usd or 0.0),
                "horizonMinutes": float(request.horizon_minutes or 0.0),
                "confidence": float(request.confidence or 0.0),
                "approved": bool(decision.approved),
                "reasonCode": str(decision.reason_code or "prime_allocation_denied"),
                "borrowCostBps": float(decision.borrow_cost_bps or 0.0),
                "requiresOperatorReview": bool(decision.requires_operator_review),
                "inventoryTracked": bool(decision_details.get("inventoryTracked", False)),
                "inventoryAvailableUsd": float(
                    decision_details.get("inventoryAvailableUsd") or 0.0
                ),
                "requiredCollateralUsd": float(
                    decision_details.get("requiredCollateralUsd") or 0.0
                ),
                "primeCapacityUsd": float(decision_details.get("primeCapacityUsd") or 0.0),
                "capacityRemainingUsd": float(decision_details.get("capacityRemainingUsd") or 0.0),
                "familyCapUsd": float(decision_details.get("familyCapUsd") or 0.0),
                "projectedFamilyExposureUsd": float(
                    decision_details.get("projectedFamilyExposureUsd") or 0.0
                ),
            },
        )
        return self._write_ledger_transaction(tx)

    def _build_prime_lifecycle_transaction(
        self,
        *,
        event: str,
        loan: Dict[str, Any],
        realized_pnl_usd: float = 0.0,
        receipt_id: str = "",
    ) -> Dict[str, Any]:
        tx = self._ledger.build_transaction(
            tx_type=str(event),
            chain=self.chain,
            receipt_id=str(receipt_id or ""),
            lines=self._prime_journal_lines(loan=loan, opened=str(event) == "prime_loan_open"),
            metadata={
                "loanId": str(loan.get("loan_id") or ""),
                "family": str(loan.get("family") or ""),
                "asset": str(loan.get("asset") or ""),
                "notionalUsd": float(loan.get("notional_usd") or 0.0),
                "borrowCostUsd": float(loan.get("borrow_cost_usd") or 0.0),
                "collateralReservedUsd": float(
                    loan.get("collateral_reserved_usd") or loan.get("notional_usd") or 0.0
                ),
                "collateralRatio": float(loan.get("collateral_ratio") or 1.0),
                "collateralHaircutPct": float(loan.get("collateral_haircut_pct") or 0.0),
                "collateralEfficiency": float(loan.get("collateral_efficiency") or 1.0),
                "status": str(loan.get("status") or ""),
                "openedTsMs": int(loan.get("opened_ts_ms") or 0),
                "settledTsMs": int(loan.get("settled_ts_ms") or 0),
                "disputedTsMs": int(loan.get("disputed_ts_ms") or 0),
                "disputeReasonCode": str(loan.get("dispute_reason_code") or ""),
                "realizedPnlUsd": float(realized_pnl_usd or 0.0),
            },
        )
        return tx.to_dict()

    def _build_prime_settlement_rejection_transaction(
        self,
        *,
        loan_id: str,
        loan: Dict[str, Any] | None,
        reason_code: str,
        realized_pnl_usd: float = 0.0,
        receipt_id: str = "",
    ) -> Dict[str, Any]:
        payload = dict(loan or {})
        family = str(payload.get("family") or "")
        note = f"prime_loan_settlement_rejected:{str(reason_code or 'prime_settlement_denied')}"
        tx = self._ledger.build_transaction(
            tx_type="prime_loan_settlement_rejected",
            chain=self.chain,
            receipt_id=str(receipt_id or ""),
            lines=[
                LedgerLine(
                    account="internal_prime:settlement_audit",
                    asset="",
                    amount=0.0,
                    family=family,
                    note=note,
                ),
                LedgerLine(account="equity:offset", asset="", amount=0.0, family=family, note=note),
            ],
            metadata={
                "loanId": str(loan_id or payload.get("loan_id") or ""),
                "family": family,
                "asset": str(payload.get("asset") or ""),
                "notionalUsd": float(payload.get("notional_usd") or 0.0),
                "borrowCostUsd": float(payload.get("borrow_cost_usd") or 0.0),
                "collateralReservedUsd": float(
                    payload.get("collateral_reserved_usd") or payload.get("notional_usd") or 0.0
                ),
                "collateralRatio": float(payload.get("collateral_ratio") or 1.0),
                "collateralHaircutPct": float(payload.get("collateral_haircut_pct") or 0.0),
                "collateralEfficiency": float(payload.get("collateral_efficiency") or 1.0),
                "status": str(payload.get("status") or ""),
                "openedTsMs": int(payload.get("opened_ts_ms") or 0),
                "settledTsMs": int(payload.get("settled_ts_ms") or 0),
                "disputedTsMs": int(payload.get("disputed_ts_ms") or 0),
                "disputeReasonCode": str(payload.get("dispute_reason_code") or ""),
                "realizedPnlUsd": float(realized_pnl_usd or 0.0),
                "reasonCode": str(reason_code or "prime_settlement_denied"),
            },
        )
        return tx.to_dict()

    def _build_prime_dispute_transaction(
        self,
        *,
        loan: Dict[str, Any],
        reason_code: str,
        receipt_id: str = "",
    ) -> Dict[str, Any]:
        payload = dict(loan or {})
        family = str(payload.get("family") or "")
        note = f"prime_loan_disputed:{str(reason_code or 'prime_loan_disputed')}"
        tx = self._ledger.build_transaction(
            tx_type="prime_loan_disputed",
            chain=self.chain,
            receipt_id=str(receipt_id or ""),
            lines=[
                LedgerLine(
                    account="internal_prime:lifecycle_audit",
                    asset="",
                    amount=0.0,
                    family=family,
                    note=note,
                ),
                LedgerLine(account="equity:offset", asset="", amount=0.0, family=family, note=note),
            ],
            metadata={
                "loanId": str(payload.get("loan_id") or ""),
                "family": family,
                "asset": str(payload.get("asset") or ""),
                "notionalUsd": float(payload.get("notional_usd") or 0.0),
                "borrowCostUsd": float(payload.get("borrow_cost_usd") or 0.0),
                "collateralReservedUsd": float(
                    payload.get("collateral_reserved_usd") or payload.get("notional_usd") or 0.0
                ),
                "collateralRatio": float(payload.get("collateral_ratio") or 1.0),
                "collateralHaircutPct": float(payload.get("collateral_haircut_pct") or 0.0),
                "collateralEfficiency": float(payload.get("collateral_efficiency") or 1.0),
                "status": str(payload.get("status") or ""),
                "openedTsMs": int(payload.get("opened_ts_ms") or 0),
                "settledTsMs": int(payload.get("settled_ts_ms") or 0),
                "disputedTsMs": int(payload.get("disputed_ts_ms") or 0),
                "disputeReasonCode": str(
                    payload.get("dispute_reason_code") or reason_code or "prime_loan_disputed"
                ),
                "reasonCode": str(reason_code or "prime_loan_disputed"),
            },
        )
        return tx.to_dict()

    def _record_prime_lifecycle_event(
        self,
        *,
        event: str,
        loan: Dict[str, Any],
        realized_pnl_usd: float = 0.0,
    ) -> Dict[str, Any]:
        tx = self._build_prime_lifecycle_transaction(
            event=event,
            loan=loan,
            realized_pnl_usd=realized_pnl_usd,
        )
        return self._write_ledger_transaction(self._tx_dict_to_transaction(tx))

    def _record_prime_settlement_rejection(
        self,
        *,
        loan_id: str,
        loan: Dict[str, Any] | None,
        reason_code: str,
        realized_pnl_usd: float = 0.0,
    ) -> Dict[str, Any]:
        tx = self._build_prime_settlement_rejection_transaction(
            loan_id=loan_id,
            loan=loan,
            reason_code=reason_code,
            realized_pnl_usd=realized_pnl_usd,
        )
        return self._write_ledger_transaction(self._tx_dict_to_transaction(tx))

    def _record_prime_dispute_event(
        self,
        *,
        loan: Dict[str, Any],
        reason_code: str,
    ) -> Dict[str, Any]:
        tx = self._build_prime_dispute_transaction(loan=loan, reason_code=reason_code)
        return self._write_ledger_transaction(self._tx_dict_to_transaction(tx))

    def _capacity_limit(self, stage_policy: Dict[str, Any] | None = None) -> float:
        if stage_policy is None:
            return max(1.0, float(self._capacity_usd or 10_000_000.0))
        return max(
            1.0,
            float(
                stage_policy.get("prime_capacity_usd", self._capacity_usd)
                or self._capacity_usd
                or 10_000_000.0
            ),
        )

    def _recompute_utilization(self, *, capacity_usd: float | None = None) -> None:
        denom = max(
            1.0, float(capacity_usd if capacity_usd is not None else self._capacity_limit())
        )
        self._utilization = min(1.0, max(0.0, self._borrowed_usd / denom))

    def _family_cap(self, req: PrimeBorrowRequest, stage_policy: Dict[str, Any]) -> float:
        capacity_usd = self._capacity_limit(stage_policy)
        deployable = float(stage_policy.get("max_deployable_pct", 0.35) or 0.35) * capacity_usd
        family_cap = (
            float(
                stage_policy.get("family_cap_pct", stage_policy.get("max_family_pct", 0.25)) or 0.25
            )
            * capacity_usd
        )
        return max(0.0, min(capacity_usd, deployable, family_cap))

    def _collateral_policy(
        self, req: PrimeBorrowRequest, stage_policy: Dict[str, Any]
    ) -> Dict[str, float]:
        notional = max(0.0, float(req.notional_usd or 0.0))
        efficiency = float(stage_policy.get("collateral_efficiency", 1.0) or 1.0)
        efficiency = max(0.05, min(1.0, efficiency))
        haircut_pct = max(0.0, float(stage_policy.get("collateral_haircut_pct", 0.0) or 0.0))
        min_ratio = max(1.0, float(stage_policy.get("min_collateral_ratio", 1.0) or 1.0))
        ratio = max(min_ratio, 1.0 / efficiency)
        ratio = round(ratio * (1.0 + haircut_pct / 100.0), 8)
        required = round(notional * ratio, 8)
        return {
            "collateralEfficiency": round(efficiency, 8),
            "collateralHaircutPct": round(haircut_pct, 8),
            "collateralRatio": round(ratio, 8),
            "requiredCollateralUsd": required,
        }

    def _decision_context(
        self, req: PrimeBorrowRequest, stage_policy: Dict[str, Any]
    ) -> Dict[str, Any]:
        asset = str(req.asset or "")
        inventory_snapshot = self.inventory.snapshot()
        collateral_policy = self._collateral_policy(req, stage_policy)
        capacity_usd = self._capacity_limit(stage_policy)
        family_cap_usd = self._family_cap(req, stage_policy)
        current_family_exposure_usd = float(self._family_exposure.get(req.family, 0.0) or 0.0)
        projected_family_exposure_usd = current_family_exposure_usd + float(req.notional_usd or 0.0)
        inventory_tracked = bool(asset and asset in inventory_snapshot)
        inventory_available_usd = (
            float(inventory_snapshot.get(asset) or 0.0) if inventory_tracked else 0.0
        )
        return {
            "detailsVersion": 2,
            "request": req.to_dict(),
            "collateralPolicy": collateral_policy,
            "inventoryTracked": inventory_tracked,
            "inventoryAvailableUsd": round(inventory_available_usd, 8),
            "requiredCollateralUsd": round(
                float(collateral_policy.get("requiredCollateralUsd") or 0.0),
                8,
            ),
            "currentBorrowedUsd": round(float(self._borrowed_usd or 0.0), 8),
            "primeCapacityUsd": round(float(capacity_usd), 8),
            "capacityRemainingUsd": round(
                max(0.0, float(capacity_usd) - float(self._borrowed_usd or 0.0)),
                8,
            ),
            "currentFamilyExposureUsd": round(current_family_exposure_usd, 8),
            "projectedFamilyExposureUsd": round(projected_family_exposure_usd, 8),
            "familyCapUsd": round(float(family_cap_usd), 8),
            "stateReady": bool(self._state_ready),
            "stateStatus": str(
                self._state_status or ("ok" if self._state_ready else "unavailable")
            ),
            "stateReasonCode": str(
                self._state_reason_code or ("" if self._state_ready else "prime_state_unavailable")
            ),
        }

    def _approve(
        self,
        req: PrimeBorrowRequest,
        *,
        stage_policy: Dict[str, Any],
        reserve_inventory: bool = True,
    ) -> CapitalDecision:
        context = self._decision_context(req, stage_policy)
        min_confidence = float(stage_policy.get("min_confidence", 0.75) or 0.75)
        context["requiredConfidence"] = float(min_confidence)
        if float(req.confidence) < min_confidence:
            return CapitalDecision(
                approved=False,
                reason_code="confidence_too_low",
                borrow_cost_bps=0.0,
                details=context,
            )
        cap = float(context.get("familyCapUsd") or 0.0)
        projected_family = float(context.get("projectedFamilyExposureUsd") or 0.0)
        if projected_family > cap:
            raise BorrowLimitError("family cap exceeded", reason_code="family_cap_exceeded")
        capacity_usd = float(context.get("primeCapacityUsd") or 0.0)
        if float(self._borrowed_usd) + float(req.notional_usd) > capacity_usd:
            raise CapitalAllocationError(
                "prime capacity exceeded", reason_code="prime_capacity_exceeded"
            )
        asset = str(req.asset or "")
        if not asset or not bool(context.get("inventoryTracked", False)):
            raise CollateralInsufficiencyError(
                "untracked inventory asset", reason_code="inventory_untracked"
            )
        inventory_available = float(context.get("inventoryAvailableUsd") or 0.0)
        if inventory_available < float(req.notional_usd):
            raise CollateralInsufficiencyError(
                "insufficient inventory", reason_code="inventory_insufficient"
            )
        required_collateral_usd = float(context.get("requiredCollateralUsd") or 0.0)
        if inventory_available + 1e-9 < required_collateral_usd:
            raise CollateralInsufficiencyError(
                "insufficient collateral", reason_code="collateral_insufficiency"
            )
        cost = internal_borrow_cost(
            notional_usd=req.notional_usd,
            horizon_minutes=req.horizon_minutes,
            utilization=self._utilization,
        )
        return CapitalDecision(
            approved=True,
            reason_code="ok",
            borrow_cost_bps=float(cost.get("borrowBps") or 0.0),
            details={
                **context,
                "borrowCostUsd": float(cost["borrowCostUsd"]),
            },
        )

    def preview(self, req: PrimeBorrowRequest, *, stage_policy: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if hasattr(self, "_approve"):
                decision = self._approve(req, stage_policy=stage_policy, reserve_inventory=False)
                return {
                    "allowed": bool(decision.approved),
                    "reason": str(
                        decision.reason_code
                        or ("ok" if decision.approved else "prime_allocation_denied")
                    ),
                    "decision": decision.to_dict() if hasattr(decision, "to_dict") else {},
                    "borrowCostUsd": float(
                        (getattr(decision, "details", {}) or {}).get("borrowCostUsd") or 0.0
                    ),
                    "utilization": float(getattr(self, "_utilization", 0.0) or 0.0),
                    "request": req.to_dict(),
                    "preview": True,
                }
        except (BorrowLimitError, CapitalAllocationError, CollateralInsufficiencyError) as exc:
            reason_code = getattr(exc, "reason_code", "prime_allocation_denied")
            return {
                "allowed": False,
                "reason": str(reason_code),
                "decision": {
                    "approved": False,
                    "reason_code": str(reason_code),
                    "details": req.to_dict(),
                },
                "borrowCostUsd": 0.0,
                "utilization": float(getattr(self, "_utilization", 0.0) or 0.0),
                "request": req.to_dict(),
                "preview": True,
            }
        return {
            "allowed": False,
            "reason": "prime_allocation_denied",
            "decision": {
                "approved": False,
                "reason_code": "prime_allocation_denied",
                "details": req.to_dict(),
            },
            "borrowCostUsd": 0.0,
            "utilization": float(getattr(self, "_utilization", 0.0) or 0.0),
            "request": req.to_dict(),
            "preview": True,
        }

    def prepare_open_transition(
        self,
        req: PrimeBorrowRequest,
        *,
        stage_policy: Dict[str, Any],
        decision: CapitalDecision,
        loan_id: str = "",
    ) -> Dict[str, Any]:
        if not bool(self._state_ready):
            return {
                "ok": False,
                "reason_code": str(self._state_reason_code or "prime_state_unavailable"),
                "loan": {},
                "journal_tx": {},
                "state_snapshot": {},
                "event_type": "prime_state",
            }

        effective_loan_id = str(loan_id or req.request_id or f"loan_{uuid.uuid4().hex[:16]}")
        collateral_policy = dict((decision.details or {}).get("collateralPolicy") or {})
        collateral_reserved_usd = float(
            collateral_policy.get("requiredCollateralUsd") or float(req.notional_usd)
        )
        pos = PrimeLoanPosition(
            loan_id=effective_loan_id,
            family=req.family,
            asset=req.asset,
            notional_usd=float(req.notional_usd),
            borrow_cost_usd=float((decision.details or {}).get("borrowCostUsd") or 0.0),
            opened_ts_ms=int(time.time() * 1000),
            collateral_reserved_usd=collateral_reserved_usd,
            collateral_ratio=float(collateral_policy.get("collateralRatio") or 1.0),
            collateral_haircut_pct=float(collateral_policy.get("collateralHaircutPct") or 0.0),
            collateral_efficiency=float(collateral_policy.get("collateralEfficiency") or 1.0),
        )

        inventory_snapshot = self.inventory.snapshot()
        inventory_seeded = inventory_snapshot.get(req.asset) is not None
        if (
            inventory_seeded
            and float(inventory_snapshot.get(req.asset) or 0.0) < collateral_reserved_usd
        ):
            return {
                "ok": False,
                "reason_code": "inventory_insufficient",
                "loan": {},
                "journal_tx": {},
                "state_snapshot": {},
                "event_type": "prime_state",
            }

        mutated_loans = deepcopy(self._loans)
        mutated_family_exposure = deepcopy(self._family_exposure)
        mutated_inventory = dict(inventory_snapshot or {})
        if inventory_seeded:
            mutated_inventory[str(req.asset)] = round(
                float(mutated_inventory.get(str(req.asset), 0.0)) - collateral_reserved_usd, 8
            )
        borrowed_usd = float(self._borrowed_usd) + float(req.notional_usd)
        mutated_family_exposure[req.family] = float(
            mutated_family_exposure.get(req.family, 0.0)
        ) + float(req.notional_usd)
        capacity_usd = self._capacity_limit(stage_policy)
        utilization = min(1.0, max(0.0, borrowed_usd / max(1.0, float(capacity_usd))))
        mutated_loans[effective_loan_id] = pos.to_dict()
        state_snapshot = self._state_snapshot_payload_from_raw(
            {
                "utilization": round(utilization, 8),
                "borrowedUsd": round(borrowed_usd, 8),
                "capacityUsd": round(float(capacity_usd), 8),
                "familyExposure": {k: round(v, 8) for k, v in mutated_family_exposure.items()},
                "loans": mutated_loans,
                "inventory": mutated_inventory,
                "updatedTsMs": int(pos.opened_ts_ms or int(time.time() * 1000)),
                "stateReady": bool(self._state_ready),
                "stateStatus": str(
                    self._state_status or ("ok" if self._state_ready else "unavailable")
                ),
                "stateReasonCode": str(self._state_reason_code or ""),
                "stateReason": str(self._state_reason or self._state_reason_code or ""),
            }
        )
        return {
            "ok": True,
            "reason_code": "ok",
            "loan": pos.to_dict(),
            "utilization": round(utilization, 6),
            "journal_tx": self._build_prime_lifecycle_transaction(
                event="prime_loan_open",
                loan=pos.to_dict(),
            ),
            "state_snapshot": state_snapshot,
            "event_type": "prime_state",
        }

    def allocate(self, req: PrimeBorrowRequest, *, stage_policy: Dict[str, Any]) -> Dict[str, Any]:
        def _denied_payload(decision: CapitalDecision) -> Dict[str, Any]:
            payload = {
                "allowed": False,
                "reason": str(decision.reason_code or "prime_allocation_denied"),
                "decision": decision.to_dict(),
                "borrowCostUsd": 0.0,
                "utilization": round(self._utilization, 6),
                "request": req.to_dict(),
            }
            try:
                payload["ledgerTransaction"] = self._record_prime_decision_event(
                    event="prime_loan_rejected",
                    request=req,
                    decision=decision,
                )
                payload["auditRecorded"] = True
            except (OSError, RuntimeError, TypeError, ValueError, LedgerConsistencyError):
                payload["auditRecorded"] = False
                payload["auditReasonCode"] = "prime_rejection_audit_failed"
            return payload

        if not bool(self._state_ready):
            return _denied_payload(
                CapitalDecision(
                    approved=False,
                    reason_code=str(self._state_reason_code or "prime_state_unavailable"),
                    details=self._decision_context(req, stage_policy),
                )
            )

        try:
            decision = self._approve(req, stage_policy=stage_policy)
        except (BorrowLimitError, CapitalAllocationError, CollateralInsufficiencyError) as exc:
            return _denied_payload(
                CapitalDecision(
                    approved=False,
                    reason_code=getattr(exc, "reason_code", "prime_allocation_denied"),
                    details=self._decision_context(req, stage_policy),
                )
            )
        if not bool(decision.approved):
            return _denied_payload(decision)
        transition = self.prepare_open_transition(
            req,
            stage_policy=dict(stage_policy or {}),
            decision=decision,
            loan_id=str(req.request_id or f"loan_{uuid.uuid4().hex[:16]}"),
        )
        if not bool(transition.get("ok", False)):
            reason_code = str(transition.get("reason_code") or "prime_allocation_denied")
            return {
                "allowed": False,
                "reason": reason_code,
                "decision": CapitalDecision(
                    approved=False,
                    reason_code=reason_code,
                    details=req.to_dict(),
                ).to_dict(),
                "borrowCostUsd": 0.0,
                "utilization": round(self._utilization, 6),
                "request": req.to_dict(),
            }

        coordinator = getattr(self, "_capital_write_service", None)
        if coordinator is not None and hasattr(coordinator, "commit_internal_prime_open"):
            try:
                committed = dict(
                    coordinator.commit_internal_prime_open(self, transition=transition) or {}
                )
            except (OSError, TypeError, ValueError, RuntimeError, LedgerConsistencyError) as exc:
                reason_code = str(getattr(exc, "reason_code", "prime_open_commit_failed"))
                return {
                    "allowed": False,
                    "reason": reason_code,
                    "decision": CapitalDecision(
                        approved=False,
                        reason_code=reason_code,
                        details=req.to_dict(),
                    ).to_dict(),
                    "borrowCostUsd": 0.0,
                    "utilization": round(self._utilization, 6),
                    "request": req.to_dict(),
                }
            loan_payload = dict(committed.get("loan") or transition.get("loan") or {})
            return {
                "allowed": True,
                "reason": "ok",
                "decision": decision.to_dict(),
                "borrowCostUsd": float(loan_payload.get("borrow_cost_usd") or 0.0),
                "utilization": float(
                    committed.get("utilization") or transition.get("utilization") or 0.0
                ),
                "request": req.to_dict(),
                "loan": loan_payload,
                "ledgerTransaction": dict(
                    committed.get("ledgerTransaction") or transition.get("journal_tx") or {}
                ),
            }

        loan_id = str(
            (transition.get("loan") or {}).get("loan_id")
            or req.request_id
            or f"loan_{uuid.uuid4().hex[:16]}"
        )
        collateral_reserved_usd = float(
            (
                (transition.get("loan") or {}).get("collateral_reserved_usd")
                or float(req.notional_usd)
            )
        )
        pos = PrimeLoanPosition(**dict(transition.get("loan") or {}))
        previous_borrowed = float(self._borrowed_usd)
        previous_capacity = float(self._capacity_usd)
        previous_family_exposure = deepcopy(self._family_exposure)
        previous_loans = deepcopy(self._loans)
        previous_utilization = float(self._utilization)
        inventory_seeded = self.inventory.snapshot().get(req.asset) is not None
        inventory_reserved = False
        state_persisted = False
        try:
            if inventory_seeded:
                self.inventory.reserve(req.asset, collateral_reserved_usd, strict=True)
                inventory_reserved = True
            self._borrowed_usd += float(req.notional_usd)
            self._family_exposure[req.family] = float(
                self._family_exposure.get(req.family, 0.0)
            ) + float(req.notional_usd)
            self._capacity_usd = self._capacity_limit(stage_policy)
            self._recompute_utilization(capacity_usd=self._capacity_usd)
            self._loans[loan_id] = pos.to_dict()
            self._state_updated_ts_ms = int(pos.opened_ts_ms or int(time.time() * 1000))
            self._save_state()
            state_persisted = True
            journal_tx = self._record_prime_lifecycle_event(
                event="prime_loan_open", loan=pos.to_dict()
            )
            self._record_state_snapshot(self._raw_state_payload(), state_type="prime_state")
        except (
            OSError,
            TypeError,
            ValueError,
            RuntimeError,
            CollateralInsufficiencyError,
            LedgerConsistencyError,
        ) as exc:
            self._borrowed_usd = previous_borrowed
            self._capacity_usd = previous_capacity
            self._family_exposure = previous_family_exposure
            self._loans = previous_loans
            self._utilization = previous_utilization
            rollback_reason_code = ""
            if inventory_reserved:
                _rollback_ok, rollback_reason_code = self._rollback_release_reserved_inventory(
                    req.asset, collateral_reserved_usd
                )
            try:
                self._save_state()
            except (OSError, TypeError, ValueError, RuntimeError):
                pass
            if rollback_reason_code:
                self._mark_state_unavailable(reason_code=rollback_reason_code)
            reason_code = getattr(
                exc,
                "reason_code",
                "prime_journal_write_failed" if state_persisted else "prime_state_persist_failed",
            )
            if rollback_reason_code:
                reason_code = rollback_reason_code
            return {
                "allowed": False,
                "reason": str(reason_code),
                "decision": CapitalDecision(
                    approved=False,
                    reason_code=str(reason_code),
                    details=req.to_dict(),
                ).to_dict(),
                "borrowCostUsd": 0.0,
                "utilization": round(self._utilization, 6),
                "request": req.to_dict(),
            }
        return {
            "allowed": True,
            "reason": "ok",
            "decision": decision.to_dict(),
            "borrowCostUsd": float(pos.borrow_cost_usd),
            "utilization": round(self._utilization, 6),
            "request": req.to_dict(),
            "loan": pos.to_dict(),
            "ledgerTransaction": journal_tx,
        }

    def settle(self, loan_id: str, *, realized_pnl_usd: float = 0.0) -> Dict[str, Any]:
        def _rejected_payload(
            *, reason_code: str, loan_payload: Dict[str, Any] | None
        ) -> Dict[str, Any]:
            payload = {"ok": False, "reason_code": str(reason_code)}
            try:
                payload["ledgerTransaction"] = self._record_prime_settlement_rejection(
                    loan_id=str(loan_id),
                    loan=loan_payload,
                    reason_code=str(reason_code),
                    realized_pnl_usd=realized_pnl_usd,
                )
                payload["auditRecorded"] = True
            except (OSError, RuntimeError, TypeError, ValueError, LedgerConsistencyError):
                payload["auditRecorded"] = False
                payload["auditReasonCode"] = "prime_settlement_rejection_audit_failed"
            return payload

        if not bool(self._state_ready):
            return _rejected_payload(
                reason_code=str(self._state_reason_code or "prime_state_unavailable"),
                loan_payload={},
            )

        loan = dict(self._loans.get(str(loan_id)) or {})
        if not loan:
            return _rejected_payload(reason_code="unknown_loan", loan_payload={})
        loan_status = str(loan.get("status") or "")
        if loan_status not in {"open", "disputed"}:
            return _rejected_payload(reason_code="loan_already_settled", loan_payload=loan)
        family = str(loan.get("family") or "")
        notional = float(loan.get("notional_usd") or 0.0)
        asset = str(loan.get("asset") or "")
        inventory_snapshot = self.inventory.snapshot()
        if asset and asset not in inventory_snapshot:
            previous_loans = deepcopy(self._loans)
            disputed_loan = dict(loan)
            disputed_loan["status"] = "disputed"
            disputed_loan["disputed_ts_ms"] = int(time.time() * 1000)
            disputed_loan["dispute_reason_code"] = "inventory_untracked_on_settlement"
            self._loans[str(loan_id)] = disputed_loan
            self._state_updated_ts_ms = int(
                disputed_loan.get("disputed_ts_ms") or int(time.time() * 1000)
            )
            try:
                self._save_state()
                journal_tx = self._record_prime_dispute_event(
                    loan=disputed_loan,
                    reason_code="inventory_untracked_on_settlement",
                )
                self._record_state_snapshot(self._raw_state_payload(), state_type="prime_state")
            except (OSError, TypeError, ValueError, RuntimeError, LedgerConsistencyError):
                self._loans = previous_loans
                try:
                    self._save_state()
                except (OSError, TypeError, ValueError, RuntimeError):
                    pass
                return _rejected_payload(
                    reason_code="inventory_untracked_on_settlement", loan_payload=loan
                )
            return {
                "ok": False,
                "reason_code": "inventory_untracked_on_settlement",
                "loan": disputed_loan,
                "ledgerTransaction": journal_tx,
                "auditRecorded": True,
            }
        previous_borrowed = float(self._borrowed_usd)
        previous_capacity = float(self._capacity_usd)
        previous_family_exposure = deepcopy(self._family_exposure)
        previous_loans = deepcopy(self._loans)
        previous_utilization = float(self._utilization)
        released_inventory = False
        state_persisted = False
        try:
            loan["status"] = "settled"
            loan["settled_ts_ms"] = int(time.time() * 1000)
            self._loans[str(loan_id)] = loan
            self._state_updated_ts_ms = int(loan.get("settled_ts_ms") or int(time.time() * 1000))
            self._borrowed_usd = max(0.0, self._borrowed_usd - notional)
            self._family_exposure[family] = max(
                0.0, float(self._family_exposure.get(family, 0.0)) - notional
            )
            self._recompute_utilization()
            collateral_reserved_usd = float(loan.get("collateral_reserved_usd") or notional)
            if asset:
                self.inventory.release(asset, collateral_reserved_usd)
                released_inventory = True
            self._save_state()
            state_persisted = True
            journal_tx = self._record_prime_lifecycle_event(
                event="prime_loan_settlement",
                loan=loan,
                realized_pnl_usd=realized_pnl_usd,
            )
            self._record_state_snapshot(self._raw_state_payload(), state_type="prime_state")
        except (OSError, TypeError, ValueError, RuntimeError, LedgerConsistencyError) as exc:
            self._borrowed_usd = previous_borrowed
            self._capacity_usd = previous_capacity
            self._family_exposure = previous_family_exposure
            self._loans = previous_loans
            self._utilization = previous_utilization
            collateral_reserved_usd = float(loan.get("collateral_reserved_usd") or notional)
            rollback_reason_code = ""
            if asset and released_inventory:
                _rollback_ok, rollback_reason_code = self._rollback_reserve_released_inventory(
                    asset, collateral_reserved_usd
                )
            try:
                self._save_state()
            except (OSError, TypeError, ValueError, RuntimeError):
                pass
            if rollback_reason_code:
                self._mark_state_unavailable(reason_code=rollback_reason_code)
            reason_code = str(
                getattr(
                    exc,
                    "reason_code",
                    (
                        "prime_settlement_journal_write_failed"
                        if state_persisted
                        else "prime_settlement_persist_failed"
                    ),
                )
            )
            if rollback_reason_code:
                reason_code = rollback_reason_code
            return {
                "ok": False,
                "reason_code": reason_code,
            }
        return {
            "ok": True,
            "loan": loan,
            "realizedPnlUsd": float(realized_pnl_usd),
            "utilization": round(self._utilization, 6),
            "ledgerTransaction": journal_tx,
        }

    def prepare_settlement_transition(
        self,
        loan_id: str,
        *,
        realized_pnl_usd: float = 0.0,
        receipt_id: str = "",
    ) -> Dict[str, Any]:
        if not bool(self._state_ready):
            return {
                "ok": False,
                "reason_code": str(self._state_reason_code or "prime_state_unavailable"),
                "journal_tx": self._build_prime_settlement_rejection_transaction(
                    loan_id=str(loan_id),
                    loan={},
                    reason_code=str(self._state_reason_code or "prime_state_unavailable"),
                    realized_pnl_usd=realized_pnl_usd,
                    receipt_id=str(receipt_id or ""),
                ),
                "state_snapshot": None,
            }

        loan = dict(self._loans.get(str(loan_id)) or {})
        if not loan:
            return {
                "ok": False,
                "reason_code": "unknown_loan",
                "journal_tx": self._build_prime_settlement_rejection_transaction(
                    loan_id=str(loan_id),
                    loan={},
                    reason_code="unknown_loan",
                    realized_pnl_usd=realized_pnl_usd,
                    receipt_id=str(receipt_id or ""),
                ),
                "state_snapshot": None,
            }
        loan_status = str(loan.get("status") or "")
        if loan_status not in {"open", "disputed"}:
            return {
                "ok": False,
                "reason_code": "loan_already_settled",
                "journal_tx": self._build_prime_settlement_rejection_transaction(
                    loan_id=str(loan_id),
                    loan=loan,
                    reason_code="loan_already_settled",
                    realized_pnl_usd=realized_pnl_usd,
                    receipt_id=str(receipt_id or ""),
                ),
                "state_snapshot": None,
            }

        family = str(loan.get("family") or "")
        notional = float(loan.get("notional_usd") or 0.0)
        asset = str(loan.get("asset") or "")
        inventory_snapshot = self.inventory.snapshot()
        mutated_loans = deepcopy(self._loans)
        mutated_family_exposure = deepcopy(self._family_exposure)
        mutated_inventory = dict(inventory_snapshot or {})
        state_updated_ts_ms = int(time.time() * 1000)

        if asset and asset not in inventory_snapshot:
            disputed_loan = dict(loan)
            disputed_loan["status"] = "disputed"
            disputed_loan["disputed_ts_ms"] = int(state_updated_ts_ms)
            disputed_loan["dispute_reason_code"] = "inventory_untracked_on_settlement"
            mutated_loans[str(loan_id)] = disputed_loan
            state_snapshot = self._state_snapshot_payload_from_raw(
                {
                    "utilization": round(self._utilization, 8),
                    "borrowedUsd": round(self._borrowed_usd, 8),
                    "capacityUsd": round(self._capacity_usd, 8),
                    "familyExposure": {k: round(v, 8) for k, v in mutated_family_exposure.items()},
                    "loans": mutated_loans,
                    "inventory": mutated_inventory,
                    "updatedTsMs": int(state_updated_ts_ms),
                    "stateReady": bool(self._state_ready),
                    "stateStatus": str(
                        self._state_status or ("ok" if self._state_ready else "unavailable")
                    ),
                    "stateReasonCode": str(self._state_reason_code or ""),
                    "stateReason": str(self._state_reason or self._state_reason_code or ""),
                }
            )
            return {
                "ok": False,
                "reason_code": "inventory_untracked_on_settlement",
                "loan": disputed_loan,
                "journal_tx": self._build_prime_dispute_transaction(
                    loan=disputed_loan,
                    reason_code="inventory_untracked_on_settlement",
                    receipt_id=str(receipt_id or ""),
                ),
                "state_snapshot": state_snapshot,
                "event_type": "prime_state",
                "auditRecorded": True,
            }

        settled_loan = dict(loan)
        settled_loan["status"] = "settled"
        settled_loan["settled_ts_ms"] = int(state_updated_ts_ms)
        mutated_loans[str(loan_id)] = settled_loan
        borrowed_usd = max(0.0, float(self._borrowed_usd) - notional)
        family_exposure = max(0.0, float(mutated_family_exposure.get(family, 0.0)) - notional)
        if family_exposure <= 1e-9:
            mutated_family_exposure.pop(family, None)
        else:
            mutated_family_exposure[family] = family_exposure
        collateral_reserved_usd = float(settled_loan.get("collateral_reserved_usd") or notional)
        if asset:
            mutated_inventory[str(asset)] = round(
                float(mutated_inventory.get(str(asset), 0.0)) + collateral_reserved_usd, 8
            )
        capacity_usd = float(self._capacity_usd or self._capacity_limit())
        utilization = min(1.0, max(0.0, borrowed_usd / max(1.0, capacity_usd)))
        state_snapshot = self._state_snapshot_payload_from_raw(
            {
                "utilization": round(utilization, 8),
                "borrowedUsd": round(borrowed_usd, 8),
                "capacityUsd": round(capacity_usd, 8),
                "familyExposure": {k: round(v, 8) for k, v in mutated_family_exposure.items()},
                "loans": mutated_loans,
                "inventory": mutated_inventory,
                "updatedTsMs": int(state_updated_ts_ms),
                "stateReady": bool(self._state_ready),
                "stateStatus": str(
                    self._state_status or ("ok" if self._state_ready else "unavailable")
                ),
                "stateReasonCode": str(self._state_reason_code or ""),
                "stateReason": str(self._state_reason or self._state_reason_code or ""),
            }
        )
        return {
            "ok": True,
            "reason_code": "ok",
            "loan": settled_loan,
            "realizedPnlUsd": float(realized_pnl_usd),
            "utilization": round(utilization, 6),
            "journal_tx": self._build_prime_lifecycle_transaction(
                event="prime_loan_settlement",
                loan=settled_loan,
                realized_pnl_usd=realized_pnl_usd,
                receipt_id=str(receipt_id or ""),
            ),
            "state_snapshot": state_snapshot,
            "event_type": "prime_state",
        }

    def snapshot(self) -> Dict[str, Any]:
        open_loans = [
            dict(v) for v in self._loans.values() if str((v or {}).get("status") or "") == "open"
        ]
        disputed_loans = [
            dict(v)
            for v in self._loans.values()
            if str((v or {}).get("status") or "") == "disputed"
        ]
        active_loans = [*open_loans, *disputed_loans]
        reserved_collateral_usd = round(
            sum(
                float(
                    (loan or {}).get("collateral_reserved_usd")
                    or (loan or {}).get("notional_usd")
                    or 0.0
                )
                for loan in active_loans
            ),
            8,
        )
        collateralization_ratio = round(
            (
                reserved_collateral_usd / max(1.0, float(self._borrowed_usd))
                if self._borrowed_usd > 0.0
                else 0.0
            ),
            8,
        )
        return {
            "borrowedUsd": round(self._borrowed_usd, 2),
            "capacityUsd": round(self._capacity_usd, 2),
            "utilization": round(self._utilization, 6),
            "updatedTsMs": int(self._state_updated_ts_ms or int(time.time() * 1000)),
            "inventory": self.inventory.snapshot(),
            "familyExposure": {k: round(v, 2) for k, v in self._family_exposure.items()},
            "openLoans": open_loans,
            "disputedLoans": disputed_loans,
            "loanCount": int(len(active_loans)),
            "disputedLoanCount": int(len(disputed_loans)),
            "reservedCollateralUsd": reserved_collateral_usd,
            "collateralizationRatio": collateralization_ratio,
            "stateReady": bool(self._state_ready),
            "stateStatus": str(
                self._state_status or ("ok" if self._state_ready else "unavailable")
            ),
            "stateReasonCode": str(
                self._state_reason_code or ("" if self._state_ready else "prime_state_unavailable")
            ),
            "stateReason": str(
                self._state_reason
                or self._state_reason_code
                or ("" if self._state_ready else "prime_state_unavailable")
            ),
        }
