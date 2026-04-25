from __future__ import annotations

import time
from typing import Any, Dict, Mapping

from victor_ai_bot.efficiency import EfficiencyPoint
from victor_ai_bot.execution_capture.realized_edge_metrics import realized_edge_metrics
from victor_ai_bot.execution_capture.smart_order_router import latency_class_for, size_bucket_for
from victor_ai_bot.domain_errors import LedgerConsistencyError
from victor_ai_bot.treasury.ledger import LedgerLine, TreasuryLedger
from victor_ai_bot.degraded_state_contract import attach_state_contract, contract_from_surface
from victor_ai_bot.persistence.repositories.capital_recovery_repository import (
    CapitalRecoveryRepository,
)
from victor_ai_bot.fund_os.family_identity import family_identity

_SAFE_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError, RuntimeError)


class ReceiptService:
    @staticmethod
    def _capture_meta(pending: Mapping[str, Any]) -> Dict[str, Any]:
        raw = pending.get("capture_meta")
        return dict(raw or {}) if isinstance(raw, Mapping) else {}

    @classmethod
    def _capture_metadata(cls, pending: Mapping[str, Any]) -> Dict[str, Any]:
        return dict(cls._capture_meta(pending).get("metadata") or {})

    @classmethod
    def _capture_envelope(cls, pending: Mapping[str, Any]) -> Dict[str, Any]:
        return dict(cls._capture_metadata(pending).get("envelope") or {})

    @classmethod
    def _capture_endpoint_selection(cls, pending: Mapping[str, Any]) -> Dict[str, Any]:
        return dict(cls._capture_metadata(pending).get("endpoint_selection") or {})

    @classmethod
    def _capture_route_plan(cls, pending: Mapping[str, Any]) -> Dict[str, Any]:
        return dict(cls._capture_metadata(pending).get("route_plan") or {})

    @staticmethod
    def _terminal_profitability_authority(pending: Mapping[str, Any]) -> Dict[str, Any]:
        raw = pending.get("terminal_profitability_authority")
        return dict(raw or {}) if isinstance(raw, Mapping) else {}

    @staticmethod
    def _capital_admission(pending: Mapping[str, Any]) -> Dict[str, Any]:
        raw = pending.get("capital_admission")
        return dict(raw or {}) if isinstance(raw, Mapping) else {}

    @staticmethod
    def _post_mutation_revalidation(pending: Mapping[str, Any]) -> Dict[str, Any]:
        raw = pending.get("post_mutation_revalidation")
        return dict(raw or {}) if isinstance(raw, Mapping) else {}

    @classmethod
    def _contract_profitability(cls, pending: Mapping[str, Any]) -> Dict[str, Any]:
        authority = cls._terminal_profitability_authority(pending)
        profitability = authority.get("profitability")
        if isinstance(profitability, Mapping) and profitability:
            return dict(profitability)
        post_mutation = cls._post_mutation_revalidation(pending)
        profitability = post_mutation.get("profitability")
        if isinstance(profitability, Mapping) and profitability:
            return dict(profitability)
        return {}

    @classmethod
    def _contract_expected_after_wei(cls, pending: Mapping[str, Any], fallback: int) -> int:
        profitability = cls._contract_profitability(pending)
        value = profitability.get("profit_after_costs_wei") if profitability else None
        return cls._safe_int(value, int(fallback or 0))

    @staticmethod
    def _family_projection(strategy_family: str, route_family: str) -> Dict[str, Any]:
        info = family_identity(str(strategy_family or route_family or "flashloan_atomic"))
        return {
            "routeFamily": str(route_family or ""),
            "family": str(info.get("launchFamily") or ""),
            "requestedFamily": str(info.get("requestedFamily") or ""),
            "runtimeFamily": str(info.get("runtimeFamily") or ""),
            "capitalFamily": str(info.get("capitalFamily") or ""),
            "displayFamily": str(info.get("displayName") or ""),
            "familyAliases": list(info.get("aliases") or []),
            "familyIdentity": info,
        }

    @classmethod
    def _settlement_profitability_chain(
        cls,
        *,
        pending: Mapping[str, Any],
        status: int,
        expected_after: int,
        realized_after: int,
    ) -> Dict[str, Any]:
        authority = cls._terminal_profitability_authority(pending)
        capital_admission = cls._capital_admission(pending)
        profitability = cls._contract_profitability(pending)
        resolved_expected_after = cls._contract_expected_after_wei(
            pending, int(expected_after or 0)
        )
        return {
            "terminalProfitabilityAuthority": authority,
            "terminalProfitability": profitability,
            "capitalAdmission": capital_admission,
            "expectedAfterCostsWei": str(int(resolved_expected_after)),
            "realizedAfterGasWei": str(int(max(0, realized_after)) if int(status) == 1 else 0),
        }

    @staticmethod
    def _accounting_profitability_metadata(
        profitability_chain: Mapping[str, Any], *, role: str = ""
    ) -> Dict[str, Any]:
        chain = dict(profitability_chain or {})
        authority = (
            dict(chain.get("terminalProfitabilityAuthority") or {})
            if isinstance(chain.get("terminalProfitabilityAuthority"), Mapping)
            else {}
        )
        profitability = (
            dict(chain.get("terminalProfitability") or {})
            if isinstance(chain.get("terminalProfitability"), Mapping)
            else {}
        )
        capital_admission = (
            dict(chain.get("capitalAdmission") or {})
            if isinstance(chain.get("capitalAdmission"), Mapping)
            else {}
        )
        metadata: Dict[str, Any] = {
            "terminalProfitabilityAuthority": authority,
            "terminalProfitability": profitability,
            "capitalAdmission": capital_admission,
            "profitabilityChain": chain,
        }
        if str(role or ""):
            metadata["settlementRole"] = str(role)
        return metadata

    @staticmethod
    def _realized_usd_from_wei(value: int) -> float:
        return float(value) / 1_000_000.0 if abs(float(value)) > 1000 else float(value)

    @staticmethod
    def _safe_dict(value: Any) -> Dict[str, Any]:
        return dict(value or {}) if isinstance(value, Mapping) else {}

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value or default))
        except _SAFE_EXCEPTIONS:
            return int(default)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value or default)
        except _SAFE_EXCEPTIONS:
            return float(default)

    @classmethod
    def _usd_from_micro(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(int(str(value))) / 1_000_000.0
        except _SAFE_EXCEPTIONS:
            try:
                return float(value)
            except _SAFE_EXCEPTIONS:
                return None

    @classmethod
    def _realized_after_usd(cls, decoded: Mapping[str, Any], *, status: int) -> float:
        if int(status) != 1:
            return 0.0
        usd_value = cls._usd_from_micro(decoded.get("realized_profit_after_gas_usd_micro"))
        if usd_value is not None:
            return max(0.0, float(usd_value))
        return max(
            0.0,
            cls._realized_usd_from_wei(cls._safe_int(decoded.get("realized_profit_after_gas_wei"))),
        )

    @classmethod
    def _gas_cost_usd(cls, decoded: Mapping[str, Any]) -> float:
        usd_value = cls._usd_from_micro(decoded.get("realized_gas_cost_usd_micro"))
        return max(0.0, float(usd_value or 0.0))

    @classmethod
    def _borrow_cost_usd(cls, pending: Mapping[str, Any]) -> float:
        capture_meta = cls._capture_metadata(pending)
        flashloan = dict(capture_meta.get("flashloan_resilience") or {})
        sizing = dict(flashloan.get("sizing") or {})
        loan = dict(pending.get("loan") or {}) if isinstance(pending.get("loan"), Mapping) else {}
        prime_loan = (
            dict(pending.get("prime_loan") or {})
            if isinstance(pending.get("prime_loan"), Mapping)
            else {}
        )
        candidates = [
            pending.get("borrow_cost_usd"),
            pending.get("borrowCostUsd"),
            loan.get("borrow_cost_usd"),
            loan.get("borrowCostUsd"),
            prime_loan.get("borrow_cost_usd"),
            prime_loan.get("borrowCostUsd"),
            flashloan.get("borrow_cost_usd"),
            flashloan.get("borrowCostUsd"),
            sizing.get("borrow_cost_usd"),
            sizing.get("borrowCostUsd"),
        ]
        for value in candidates:
            if value is None or value == "":
                continue
            try:
                return max(0.0, float(value))
            except _SAFE_EXCEPTIONS:
                continue
        return 0.0

    @classmethod
    def _loan_id(cls, pending: Mapping[str, Any]) -> str:
        loan = dict(pending.get("loan") or {}) if isinstance(pending.get("loan"), Mapping) else {}
        prime_loan = (
            dict(pending.get("prime_loan") or {})
            if isinstance(pending.get("prime_loan"), Mapping)
            else {}
        )
        candidates = [
            pending.get("loan_id"),
            pending.get("prime_loan_id"),
            pending.get("internal_prime_loan_id"),
            loan.get("loan_id"),
            prime_loan.get("loan_id"),
        ]
        for value in candidates:
            if value:
                return str(value)
        return ""

    @classmethod
    def _flashloan_fee_wei(cls, pending: Mapping[str, Any]) -> int:
        capture_meta = cls._capture_metadata(pending)
        flashloan = dict(capture_meta.get("flashloan_resilience") or {})
        sizing = dict(flashloan.get("sizing") or {})
        candidates = [
            pending.get("flashloan_fee_wei"),
            pending.get("flashloanFeeWei"),
            flashloan.get("flashloan_fee_wei"),
            flashloan.get("flashloanFeeWei"),
            sizing.get("flashloan_fee_wei"),
            sizing.get("flashloanFeeWei"),
        ]
        for value in candidates:
            if value is None or value == "":
                continue
            try:
                return max(0, int(str(value)))
            except _SAFE_EXCEPTIONS:
                continue
        return 0

    @classmethod
    def _borrowing_surface(
        cls,
        pending: Mapping[str, Any],
        *,
        amount_in: int,
        borrow_cost_usd: float,
        loan_result: Mapping[str, Any] | None,
    ) -> Dict[str, Any]:
        capture_meta = cls._capture_metadata(pending)
        flashloan = dict(capture_meta.get("flashloan_resilience") or {})
        sizing = dict(flashloan.get("sizing") or {})
        route_family = str(pending.get("route_family") or "")
        strategy_family = str(pending.get("strategy_family") or "")
        loan_id = cls._loan_id(pending)
        provider = str(
            flashloan.get("selected_provider")
            or flashloan.get("provider")
            or sizing.get("selected_provider")
            or sizing.get("provider")
            or ""
        )
        source = ""
        if loan_id:
            source = "internal_prime"
        elif provider or "flash" in route_family or "flash" in strategy_family:
            source = "flashloan"
        else:
            source = str(pending.get("capital_source") or "")
        return {
            "source": source,
            "loanId": str(loan_id or ""),
            "provider": provider,
            "flashloanFeeWei": int(cls._flashloan_fee_wei(pending)),
            "borrowCostUsd": round(float(borrow_cost_usd), 6),
            "amountInWei": int(amount_in),
            "loanSettlement": dict(loan_result or {}),
        }

    @staticmethod
    def _disable_runtime(
        runtime: Any,
        *,
        source: str,
        reason_code: str,
        details: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        control = getattr(runtime, "_runtime_control_service", None)
        if control is not None and hasattr(control, "enforce_runtime_disable"):
            try:
                return dict(
                    control.enforce_runtime_disable(
                        runtime,
                        source=source,
                        reason_code=reason_code,
                        details=dict(details or {}),
                        dry_run=True,
                        audit_event="runtime_disable",
                        audit_reason=reason_code,
                    )
                    or {}
                )
            except _SAFE_EXCEPTIONS:
                pass
        fallback = {
            "ok": False,
            "source": str(source or "receipt_settlement"),
            "reason_code": str(reason_code or "runtime_disable"),
            "settings": {"auto_trading": False, "dry_run": True},
            "controls": {},
            "details": dict(details or {}),
        }
        try:
            runtime._auto_trading = False
            runtime.cfg.execution.auto_trading = False
            runtime.cfg.execution.dry_run = True
        except _SAFE_EXCEPTIONS:
            pass
        runtime._last_runtime_disable_event = fallback
        return fallback

    @staticmethod
    def _repo_has_receipt_transaction(runtime: Any, *, receipt_id: str, tx_type: str) -> bool:
        repo = getattr(runtime, "_ledger_repo", None)
        if repo is None or not hasattr(repo, "has_receipt_transaction"):
            return False
        try:
            chain = str(
                getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or ""
            )
            return bool(
                repo.has_receipt_transaction(
                    chain=chain,
                    receipt_id=str(receipt_id or ""),
                    tx_type=str(tx_type or ""),
                )
            )
        except _SAFE_EXCEPTIONS:
            return False

    @staticmethod
    def _ledger_has_receipt_transaction(ledger: Any, *, receipt_id: str, tx_type: str) -> bool:
        if ledger is None or not hasattr(ledger, "transactions_all"):
            return False
        try:
            for row in list(ledger.transactions_all() or []):
                if not isinstance(row, dict):
                    continue
                if str(row.get("receipt_id") or "") != str(receipt_id or ""):
                    continue
                if str(row.get("tx_type") or "") != str(tx_type or ""):
                    continue
                return True
        except _SAFE_EXCEPTIONS:
            return False
        return False

    @staticmethod
    def _persist_ledger_transaction(runtime: Any, payload: Mapping[str, Any]) -> None:
        repo = getattr(runtime, "_ledger_repo", None)
        if repo is None or not hasattr(repo, "append_transaction"):
            return
        repo.append_transaction(
            chain=str(
                getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or ""
            ),
            payload=dict(payload or {}),
        )

    @staticmethod
    def _publish_capital_event(
        runtime: Any,
        *,
        domain: str,
        event_type: str,
        payload: Mapping[str, Any],
        source: str,
        transaction_id: str = "",
        receipt_id: str = "",
        entity_id: str = "",
    ) -> None:
        repo = getattr(runtime, "_capital_event_repo", None)
        if repo is None or not hasattr(repo, "append_event"):
            return
        payload_dict = dict(payload or {})
        try:
            repo.append_event(
                ts_ms=int(payload_dict.get("ts_ms") or int(time.time() * 1000)),
                domain=str(domain or "receipt"),
                event_type=str(event_type or "unknown"),
                source=str(source or "receipt_service"),
                transaction_id=str(transaction_id or ""),
                receipt_id=str(receipt_id or ""),
                entity_id=str(entity_id or ""),
                payload=payload_dict,
            )
        except _SAFE_EXCEPTIONS:
            return

    @staticmethod
    def _capital_recovery_repo(runtime: Any) -> CapitalRecoveryRepository | None:
        repo = getattr(runtime, "_capital_recovery_repo", None)
        if repo is not None:
            return repo
        db = getattr(runtime, "_db", None)
        if db is None:
            return None
        chain = str(
            getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or ""
        )
        repo = CapitalRecoveryRepository(db, chain=chain)
        runtime._capital_recovery_repo = repo
        return repo

    def settled_outcome_truth(self, *, status: int, decoded: Mapping[str, Any]) -> Dict[str, Any]:
        if int(status) != 1:
            return {"ok": True, "reason_code": "ok", "reason_codes": [], "verified": True}
        realized_after = self._safe_int(decoded.get("realized_profit_after_gas_wei"))
        realized_token_wei = self._safe_int(decoded.get("realized_profit_token_wei"))
        realized_usd_micro = self._safe_int(decoded.get("realized_profit_after_gas_usd_micro"))
        if any(value > 0 for value in (realized_after, realized_token_wei, realized_usd_micro)):
            return {"ok": True, "reason_code": "ok", "reason_codes": [], "verified": True}
        reason_code = "settled_profit_truth_unavailable"
        return {
            "ok": False,
            "reason_code": reason_code,
            "reason_codes": [reason_code],
            "verified": False,
        }

    def observe_outcome_truth_health(
        self,
        runtime: Any,
        *,
        verified: bool,
        reason_code: str,
        ts_ms: int | None = None,
    ) -> Dict[str, Any]:
        repo = self._capital_recovery_repo(runtime)
        if repo is None:
            return {}
        observed_ts_ms = int(ts_ms or int(time.time() * 1000))
        return dict(
            repo.observe(
                component="receipt_outcome_truth",
                degraded=not bool(verified),
                ts_ms=observed_ts_ms,
                reason_code=str(reason_code or ("ok" if verified else "degraded")),
            )
            or {}
        )

    def record_outcome_truth_gap(
        self,
        runtime: Any,
        *,
        tx_hash: str,
        route_id: str,
        status: int,
        reason_code: str,
        pending: Mapping[str, Any],
    ) -> Dict[str, Any]:
        resolved_reason_code = str(reason_code or "settled_profit_truth_unavailable")
        profitability_chain = self._settlement_profitability_chain(
            pending=dict(pending or {}),
            status=int(status),
            expected_after=self._contract_expected_after_wei(pending, 0),
            realized_after=0,
        )
        out = attach_state_contract(
            {
                "ok": False,
                "reason": resolved_reason_code,
                "receiptId": str(tx_hash),
                "routeId": str(route_id or ""),
                "status": "truth_unverified",
                "blockedAutoTrading": True,
                "terminalProfitabilityAuthority": dict(
                    profitability_chain.get("terminalProfitabilityAuthority") or {}
                ),
                "terminalProfitability": dict(
                    profitability_chain.get("terminalProfitability") or {}
                ),
                "capitalAdmission": dict(profitability_chain.get("capitalAdmission") or {}),
                "profitabilityChain": dict(profitability_chain),
            },
            phase="settlement",
            reason_code=resolved_reason_code,
            degraded=True,
            blocked=True,
            sticky_cycle=True,
        )
        disable_event = self._disable_runtime(
            runtime,
            source="receipt_settlement",
            reason_code=resolved_reason_code,
            details={"receiptId": str(tx_hash), "routeId": str(route_id or "")},
        )
        out["runtimeDisable"] = disable_event
        runtime._last_settlement_sync = out
        audit = getattr(getattr(runtime, "_cc", None), "audit", None)
        if audit is not None and hasattr(audit, "append"):
            try:
                audit.append(
                    "receipt_outcome_truth_gap",
                    {
                        "tx_hash": str(tx_hash),
                        "route_id": str(route_id or ""),
                        "status": int(status),
                        "reason_code": resolved_reason_code,
                        "profitabilityChain": dict(profitability_chain),
                    },
                    actor="system",
                    reason="receipt_outcome_truth_gap",
                )
            except _SAFE_EXCEPTIONS:
                pass
        return out

    def synchronize_settlement_accounting(
        self,
        runtime: Any,
        *,
        tx_hash: str,
        pending: Mapping[str, Any],
        decoded: Mapping[str, Any],
        status: int,
        amount_in: int,
        expected_after: int,
        realized_after: int,
        submit_to_receipt_ms: int,
        route_id: str,
        route_family: str,
        strategy_family: str,
        capture_lane_pending: str,
        outcome_truth_verified: bool = True,
        outcome_truth_reason_code: str = "ok",
    ) -> Dict[str, Any]:
        settled = getattr(runtime, "_settled_receipts", None)
        if not isinstance(settled, set):
            settled = set()
            runtime._settled_receipts = settled
        ledger = getattr(runtime, "_ledger", None)
        duplicate_receipt = (
            str(tx_hash) in settled
            or self._repo_has_receipt_transaction(
                runtime, receipt_id=str(tx_hash), tx_type="receipt_settlement"
            )
            or self._ledger_has_receipt_transaction(
                ledger, receipt_id=str(tx_hash), tx_type="receipt_settlement"
            )
        )
        if duplicate_receipt:
            settled.add(str(tx_hash))
            out = attach_state_contract(
                {"ok": True, "duplicate": True, "receiptId": str(tx_hash)},
                phase="settlement",
                reason_code="duplicate_receipt",
                degraded=False,
                sticky_cycle=True,
            )
            runtime._last_settlement_sync = out
            return out

        if ledger is None or not hasattr(ledger, "append_transaction"):
            out = attach_state_contract(
                {
                    "ok": False,
                    "reason": "ledger_unavailable",
                    "receiptId": str(tx_hash),
                    "blockedAutoTrading": True,
                },
                phase="settlement",
                reason_code="ledger_unavailable",
                degraded=True,
                blocked=True,
                sticky_cycle=True,
            )
            disable_event = self._disable_runtime(
                runtime,
                source="receipt_settlement",
                reason_code="ledger_unavailable",
                details={"receiptId": str(tx_hash)},
            )
            out["runtimeDisable"] = disable_event
            runtime._last_settlement_sync = out
            return out

        expected_after = self._contract_expected_after_wei(pending, int(expected_after or 0))
        success = bool(int(status) == 1)
        if not bool(outcome_truth_verified):
            profitability_chain = self._settlement_profitability_chain(
                pending=dict(pending or {}),
                status=int(status),
                expected_after=int(expected_after),
                realized_after=0,
            )
            out = attach_state_contract(
                {
                    "ok": False,
                    "reason": str(outcome_truth_reason_code or "settled_profit_truth_unavailable"),
                    "receiptId": str(tx_hash),
                    "routeId": str(route_id),
                    "status": "truth_unverified",
                    "blockedAutoTrading": True,
                    "terminalProfitabilityAuthority": dict(
                        profitability_chain.get("terminalProfitabilityAuthority") or {}
                    ),
                    "terminalProfitability": dict(
                        profitability_chain.get("terminalProfitability") or {}
                    ),
                    "capitalAdmission": dict(profitability_chain.get("capitalAdmission") or {}),
                    "profitabilityChain": dict(profitability_chain),
                },
                phase="settlement",
                reason_code=str(outcome_truth_reason_code or "settled_profit_truth_unavailable"),
                degraded=True,
                blocked=True,
                sticky_cycle=True,
            )
            disable_event = self._disable_runtime(
                runtime,
                source="receipt_settlement",
                reason_code=str(outcome_truth_reason_code or "settled_profit_truth_unavailable"),
                details={"receiptId": str(tx_hash), "routeId": str(route_id)},
            )
            out["runtimeDisable"] = disable_event
            runtime._last_settlement_sync = out
            return out
        realized_after_usd = self._realized_after_usd(decoded, status=int(status))
        gas_cost_wei = self._safe_int(decoded.get("realized_gas_cost_wei"))
        gas_cost_usd = self._gas_cost_usd(decoded)
        borrow_cost_usd = self._borrow_cost_usd(pending)
        settlement_loss_usd = float(gas_cost_usd) if not success else 0.0
        net_realized_usd = (
            float(realized_after_usd) - float(borrow_cost_usd) - float(settlement_loss_usd)
        )

        chain = str(
            getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or ""
        )
        venue = str(capture_lane_pending or "RECEIPT")
        note_prefix = f"receipt_settlement:{str(route_id or tx_hash)}"
        profitability_chain = self._settlement_profitability_chain(
            pending=dict(pending or {}),
            status=int(status),
            expected_after=int(expected_after),
            realized_after=int(realized_after),
        )
        accounting_profitability_metadata = self._accounting_profitability_metadata(
            profitability_chain,
            role="receipt_settlement",
        )

        capital_writer = getattr(runtime, "_capital_write_service", None)
        try:
            tx_lines = [
                LedgerLine(
                    account="asset:USD",
                    asset="USD",
                    amount=float(round(net_realized_usd, 8)),
                    family=str(strategy_family or "flashloan_atomic"),
                    venue=venue,
                    note=f"{note_prefix}:net",
                ),
                LedgerLine(
                    account="equity:offset",
                    asset="USD",
                    amount=float(round(-net_realized_usd, 8)),
                    family=str(strategy_family or "flashloan_atomic"),
                    venue=venue,
                    note=f"{note_prefix}:offset",
                ),
            ]
            tx_metadata = {
                "tx_hash": str(tx_hash),
                "status": int(status),
                "route_id": str(route_id),
                "route_family": str(route_family),
                "strategy_family": str(strategy_family),
                "capture_lane": venue,
                "amount_in_wei": int(amount_in),
                "expected_after_costs_wei": int(expected_after),
                "realized_after_gas_wei": int(realized_after) if success else 0,
                "realized_after_gas_usd": round(float(realized_after_usd), 6),
                "realized_profit_after_gas_wei": str(int(realized_after) if success else 0),
                "realized_profit_token": str(decoded.get("realized_profit_token") or "USD"),
                "realized_profit_token_wei": str(
                    self._safe_int(
                        decoded.get("realized_profit_token_wei")
                        or decoded.get("realized_profit_after_gas_wei")
                        or (int(realized_after) if success else 0)
                    )
                ),
                "realized_profit_after_gas_usd_micro": str(
                    self._safe_int(
                        decoded.get("realized_profit_after_gas_usd_micro")
                        or int(round(float(realized_after_usd) * 1_000_000.0))
                    )
                ),
                "gas_cost_wei": int(gas_cost_wei),
                "gas_cost_usd": round(float(gas_cost_usd), 6),
                "borrow_cost_usd": round(float(borrow_cost_usd), 6),
                "net_realized_usd": round(float(net_realized_usd), 6),
                "submit_to_receipt_ms": int(submit_to_receipt_ms),
                **accounting_profitability_metadata,
            }
            tx = (
                ledger.build_transaction(
                    tx_type="receipt_settlement",
                    chain=chain,
                    receipt_id=str(tx_hash),
                    lines=tx_lines,
                    metadata=tx_metadata,
                )
                if capital_writer is not None
                and hasattr(capital_writer, "commit_receipt_settlement")
                else ledger.append_transaction(
                    tx_type="receipt_settlement",
                    chain=chain,
                    receipt_id=str(tx_hash),
                    lines=tx_lines,
                    metadata=tx_metadata,
                )
            )
            if not (
                capital_writer is not None and hasattr(capital_writer, "commit_receipt_settlement")
            ):
                self._persist_ledger_transaction(runtime, tx.to_dict())
            ledger_entries = TreasuryLedger.projected_entry_rows([tx.to_dict()])
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            OSError,
            LedgerConsistencyError,
        ) as exc:
            out = attach_state_contract(
                {
                    "ok": False,
                    "reason": f"ledger_sync_failed:{type(exc).__name__}",
                    "receiptId": str(tx_hash),
                    "blockedAutoTrading": True,
                },
                phase="settlement",
                reason_code=f"ledger_sync_failed:{type(exc).__name__}",
                degraded=True,
                blocked=True,
                sticky_cycle=True,
            )
            disable_event = self._disable_runtime(
                runtime,
                source="receipt_settlement",
                reason_code=str(out.get("reason") or "ledger_sync_failed"),
                details={"receiptId": str(tx_hash)},
            )
            out["runtimeDisable"] = disable_event
            runtime._last_settlement_sync = out
            return out

        loan_result: Dict[str, Any] = {}
        prime_transition: Dict[str, Any] = {}
        loan_id = self._loan_id(pending)
        if loan_id and getattr(runtime, "_internal_prime", None) is not None:
            prime = getattr(runtime, "_internal_prime", None)
            if (
                capital_writer is not None
                and hasattr(capital_writer, "commit_receipt_settlement")
                and prime is not None
                and hasattr(prime, "prepare_settlement_transition")
            ):
                try:
                    prime_transition = dict(
                        prime.prepare_settlement_transition(
                            str(loan_id),
                            realized_pnl_usd=float(round(net_realized_usd, 6)),
                            receipt_id=str(tx_hash),
                        )
                        or {}
                    )
                    loan_result = dict(prime_transition or {})
                except _SAFE_EXCEPTIONS:
                    loan_result = {"ok": False, "reason_code": "prime_settle_prepare_failed"}
                    prime_transition = dict(loan_result)
            elif prime is not None and hasattr(prime, "settle"):
                try:
                    loan_result = dict(
                        prime.settle(
                            str(loan_id), realized_pnl_usd=float(round(net_realized_usd, 6))
                        )
                        or {}
                    )
                except _SAFE_EXCEPTIONS:
                    loan_result = {"ok": False, "reason_code": "prime_settle_failed"}
                if not bool(loan_result.get("ok", False)):
                    out = attach_state_contract(
                        {
                            "ok": False,
                            "reason": str(loan_result.get("reason_code") or "prime_settle_failed"),
                            "receiptId": str(tx_hash),
                            "blockedAutoTrading": True,
                        },
                        phase="settlement",
                        reason_code=str(loan_result.get("reason_code") or "prime_settle_failed"),
                        degraded=True,
                        blocked=True,
                        sticky_cycle=True,
                    )
                    disable_event = self._disable_runtime(
                        runtime,
                        source="receipt_settlement",
                        reason_code=str(out.get("reason") or "prime_settle_failed"),
                        details={"receiptId": str(tx_hash), "loanId": str(loan_id)},
                    )
                    out["runtimeDisable"] = disable_event
                    runtime._last_settlement_sync = out
                    return out

        borrowing = self._borrowing_surface(
            pending,
            amount_in=int(amount_in),
            borrow_cost_usd=float(borrow_cost_usd),
            loan_result=loan_result,
        )
        family_projection = self._family_projection(
            str(strategy_family or ""),
            str(route_family or ""),
        )

        treasury_snapshot: Dict[str, Any] = {}
        treasury = getattr(runtime, "_treasury", None)
        if treasury is not None and hasattr(treasury, "cfg"):
            try:
                meta = dict(getattr(getattr(treasury, "cfg", None), "meta", {}) or {})
                meta["rolling_gas_cost_wei"] = int(meta.get("rolling_gas_cost_wei") or 0) + int(
                    gas_cost_wei
                )
                meta["rolling_failures"] = int(meta.get("rolling_failures") or 0) + (
                    0 if success else 1
                )
                meta["turnover_count"] = int(meta.get("turnover_count") or 0) + 1
                meta["last_settlement_receipt_id"] = str(tx_hash)
                meta["last_settlement_status"] = "settled" if success else "failed"
                meta["last_settlement_route_id"] = str(route_id)
                meta["last_settlement_route_family"] = str(route_family)
                meta["last_settlement_strategy_family"] = str(strategy_family)
                meta["last_settlement_family"] = str(family_projection.get("family") or "")
                meta["last_settlement_runtime_family"] = str(
                    family_projection.get("runtimeFamily") or ""
                )
                meta["last_settlement_capital_family"] = str(
                    family_projection.get("capitalFamily") or ""
                )
                meta["last_settlement_display_family"] = str(
                    family_projection.get("displayFamily") or ""
                )
                meta["last_settlement_family_aliases"] = list(
                    family_projection.get("familyAliases") or []
                )
                meta["last_settlement_family_identity"] = dict(
                    family_projection.get("familyIdentity") or {}
                )
                meta["last_settlement_submit_to_receipt_ms"] = int(submit_to_receipt_ms)
                meta["last_settlement_realized_after_gas_usd"] = round(float(realized_after_usd), 6)
                meta["last_settlement_borrow_cost_usd"] = round(float(borrow_cost_usd), 6)
                meta["last_settlement_net_usd"] = round(float(net_realized_usd), 6)
                meta["last_settlement_borrowing_source"] = str(borrowing.get("source") or "")
                meta["last_settlement_flashloan_provider"] = str(borrowing.get("provider") or "")
                meta["last_settlement_flashloan_fee_wei"] = int(
                    borrowing.get("flashloanFeeWei") or 0
                )
                terminal_authority = self._terminal_profitability_authority(pending)
                terminal_profitability = (
                    dict(terminal_authority.get("profitability") or {})
                    if isinstance(terminal_authority.get("profitability"), Mapping)
                    else {}
                )
                meta["last_settlement_terminal_profitability_stage"] = str(
                    terminal_authority.get("stage") or ""
                )
                meta["last_settlement_terminal_profitability_reason"] = str(
                    terminal_authority.get("reason") or ""
                )
                meta["last_settlement_terminal_profitability_authoritative"] = bool(
                    terminal_authority.get("authoritative", False)
                )
                meta["last_settlement_terminal_profitability_live_gas_derived"] = bool(
                    terminal_authority.get("live_gas_derived", False)
                )
                meta["last_settlement_terminal_profitability_after_costs_wei"] = int(
                    self._safe_int(terminal_profitability.get("profit_after_costs_wei") or 0)
                )
                meta["last_settlement_terminal_profitability_authority"] = dict(terminal_authority)
                meta["last_settlement_terminal_profitability"] = dict(terminal_profitability)
                meta["last_settlement_capital_admission"] = self._capital_admission(pending)
                meta["last_settlement_profitability_chain"] = dict(profitability_chain)
                bankroll = getattr(runtime, "_bankroll", None)
                if bankroll is not None and hasattr(bankroll, "cfg") and hasattr(bankroll, "state"):
                    meta["auto_reinvest_enabled"] = bool(
                        getattr(bankroll.cfg, "auto_reinvest_enabled", False)
                    )
                    realized_profit_wei = int(
                        getattr(bankroll.state, "realized_profit_wei", 0) or 0
                    )
                    base_borrow = int(getattr(bankroll.cfg, "base_borrow_amount_wei", 0) or 0)
                    try:
                        next_amount = (
                            int(bankroll.next_amount_in())
                            if hasattr(bankroll, "next_amount_in")
                            else base_borrow
                        )
                    except _SAFE_EXCEPTIONS:
                        next_amount = base_borrow
                    estimated_capital = max(
                        int(meta.get("estimated_capital_wei") or 0),
                        int(realized_profit_wei) + max(int(base_borrow), int(next_amount)),
                    )
                    if estimated_capital > 0:
                        meta["estimated_capital_wei"] = int(estimated_capital)
                        if int(amount_in) > 0:
                            meta["utilization_rate"] = round(
                                max(
                                    0.0,
                                    min(1.0, float(int(amount_in)) / float(int(estimated_capital))),
                                ),
                                6,
                            )
                    meta["last_realized_profit_wei"] = int(realized_profit_wei)
                treasury.cfg.meta = meta
                if hasattr(treasury, "pre_select_strategy"):
                    bankroll_state = {
                        "realized_profit_wei": int(
                            getattr(
                                getattr(getattr(runtime, "_bankroll", None), "state", None),
                                "realized_profit_wei",
                                0,
                            )
                            or 0
                        ),
                        "last_amount_in_wei": int(amount_in or 0),
                        "success_streak": int(
                            getattr(
                                getattr(getattr(runtime, "_bankroll", None), "state", None),
                                "success_streak",
                                0,
                            )
                            or 0
                        ),
                        "fail_streak": int(
                            getattr(
                                getattr(getattr(runtime, "_bankroll", None), "state", None),
                                "fail_streak",
                                0,
                            )
                            or 0
                        ),
                        "updated_ts_ms": int(
                            getattr(
                                getattr(getattr(runtime, "_bankroll", None), "state", None),
                                "updated_ts_ms",
                                0,
                            )
                            or 0
                        ),
                        "profit_updated_ts_ms": int(
                            getattr(
                                getattr(getattr(runtime, "_bankroll", None), "state", None),
                                "profit_updated_ts_ms",
                                0,
                            )
                            or 0
                        ),
                        "sizing_updated_ts_ms": int(
                            getattr(
                                getattr(getattr(runtime, "_bankroll", None), "state", None),
                                "sizing_updated_ts_ms",
                                0,
                            )
                            or 0
                        ),
                    }
                    treasury_snapshot = dict(
                        treasury.pre_select_strategy(
                            bankroll_state=bankroll_state,
                            volatility_regime=str(
                                (getattr(runtime, "_market_regime", {}) or {}).get("regime")
                                or "balanced"
                            ),
                        )
                        or {}
                    )
                treasury_snapshot["terminalProfitabilityAuthority"] = dict(
                    profitability_chain.get("terminalProfitabilityAuthority") or {}
                )
                treasury_snapshot["terminalProfitability"] = dict(
                    profitability_chain.get("terminalProfitability") or {}
                )
                treasury_snapshot["capitalAdmission"] = dict(
                    profitability_chain.get("capitalAdmission") or {}
                )
                treasury_snapshot["profitabilityChain"] = dict(profitability_chain)
            except _SAFE_EXCEPTIONS:
                treasury_snapshot = {}

        capital_writer = getattr(runtime, "_capital_write_service", None)
        if capital_writer is not None and hasattr(capital_writer, "commit_receipt_settlement"):
            try:
                commit_result = dict(
                    capital_writer.commit_receipt_settlement(
                        runtime,
                        tx_payload=tx.to_dict(),
                        tx_lines=[line.to_dict() for line in list(tx.lines or [])],
                        receipt_id=str(tx_hash),
                        status=int(status),
                        amount_in=int(amount_in),
                        submit_to_receipt_ms=int(submit_to_receipt_ms),
                        route_id=str(route_id),
                        route_family=str(route_family),
                        strategy_family=str(strategy_family),
                        capture_lane_pending=str(capture_lane_pending),
                        realized_after_usd=float(realized_after_usd),
                        borrow_cost_usd=float(borrow_cost_usd),
                        net_realized_usd=float(net_realized_usd),
                        gas_cost_wei=int(gas_cost_wei),
                        profitability_chain=profitability_chain,
                        borrowing=borrowing,
                        loan_result=loan_result,
                        outcome_truth_verified=bool(outcome_truth_verified),
                        prime_transition=dict(prime_transition or {}),
                    )
                    or {}
                )
                ledger_entries = [
                    dict(row)
                    for row in list(commit_result.get("ledger_entries") or [])
                    if isinstance(row, dict)
                ]
                treasury_snapshot = dict(commit_result.get("treasury_snapshot") or {})
                if loan_id and prime_transition:
                    loan_result = dict(commit_result.get("prime_result") or loan_result)
                    if not bool(loan_result.get("ok", False)):
                        out = attach_state_contract(
                            {
                                "ok": False,
                                "reason": str(
                                    loan_result.get("reason_code") or "prime_settle_failed"
                                ),
                                "receiptId": str(tx_hash),
                                "blockedAutoTrading": True,
                                "settlementCommitted": True,
                            },
                            phase="settlement",
                            reason_code=str(
                                loan_result.get("reason_code") or "prime_settle_failed"
                            ),
                            degraded=True,
                            blocked=True,
                            sticky_cycle=True,
                        )
                        disable_event = self._disable_runtime(
                            runtime,
                            source="receipt_settlement",
                            reason_code=str(out.get("reason") or "prime_settle_failed"),
                            details={"receiptId": str(tx_hash), "loanId": str(loan_id)},
                        )
                        out["runtimeDisable"] = disable_event
                        out["ledgerEntries"] = list(ledger_entries)
                        runtime._last_settlement_sync = out
                        return out
            except _SAFE_EXCEPTIONS as exc:
                out = attach_state_contract(
                    {
                        "ok": False,
                        "reason": f"capital_write_failed:{type(exc).__name__}",
                        "receiptId": str(tx_hash),
                        "blockedAutoTrading": True,
                    },
                    phase="settlement",
                    reason_code=f"capital_write_failed:{type(exc).__name__}",
                    degraded=True,
                    blocked=True,
                    sticky_cycle=True,
                )
                disable_event = self._disable_runtime(
                    runtime,
                    source="receipt_settlement",
                    reason_code=str(out.get("reason") or "capital_write_failed"),
                    details={"receiptId": str(tx_hash)},
                )
                out["runtimeDisable"] = disable_event
                runtime._last_settlement_sync = out
                return out
        else:
            self._publish_capital_event(
                runtime,
                domain="receipt",
                event_type="settlement_recorded" if success else "settlement_failed",
                source="receipt_service",
                transaction_id=str(tx.transaction_id),
                receipt_id=str(tx_hash),
                entity_id=str(route_id or tx_hash),
                payload={
                    "ts_ms": int(time.time() * 1000),
                    "status": "settled" if success else "failed",
                    "route_id": str(route_id),
                    "route_family": str(route_family),
                    "strategy_family": str(strategy_family),
                    "realized_profit_after_gas_wei": int(realized_after) if success else 0,
                    "realized_after_gas_usd": round(float(realized_after_usd), 6),
                    "borrow_cost_usd": round(float(borrow_cost_usd), 6),
                    "net_realized_usd": round(float(net_realized_usd), 6),
                    "transaction_id": str(tx.transaction_id),
                },
            )

        settled.add(str(tx_hash))
        out = attach_state_contract(
            {
                "ok": True,
                "receiptId": str(tx_hash),
                "status": "settled" if success else "failed",
                "transactionId": str(tx.transaction_id),
                "entryCount": int(len(ledger_entries)),
                "realizedAfterGasUsd": round(float(realized_after_usd), 6),
                "borrowCostUsd": round(float(borrow_cost_usd), 6),
                "netRealizedUsd": round(float(net_realized_usd), 6),
                "borrowing": dict(borrowing),
                **family_projection,
                "loanSettlement": dict(loan_result or {}),
                "treasury": dict(treasury_snapshot or {}),
                "learningSync": {
                    "executed": False,
                    "ok": False,
                    "reasonCode": "pending_receipt_followthrough",
                },
                "memorySync": {
                    "executed": False,
                    "ok": False,
                    "reasonCode": "pending_receipt_followthrough",
                },
                "closedLoop": {
                    "settlementAccounting": True,
                    "learningRecorded": False,
                    "memoryRecorded": False,
                    "completed": False,
                    "reasonCodes": ["pending_receipt_followthrough"],
                    "nextAction": "finalize_receipt_followthrough",
                },
                "terminalProfitabilityAuthority": dict(
                    profitability_chain.get("terminalProfitabilityAuthority") or {}
                ),
                "terminalProfitability": dict(
                    profitability_chain.get("terminalProfitability") or {}
                ),
                "capitalAdmission": dict(profitability_chain.get("capitalAdmission") or {}),
                "profitabilityChain": dict(profitability_chain),
                "blockedAutoTrading": False,
            },
            phase="settlement",
            reason_code="settled_success" if success else "settled_failed",
            degraded=not success,
            blocked=False,
            sticky_cycle=True,
        )
        runtime._last_settlement_sync = out
        return out

    @staticmethod
    def _reward_enabled(runtime: Any) -> bool:
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        if controls is None:
            return True
        try:
            return bool(getattr(controls, "reward_trace_enabled", True))
        except _SAFE_EXCEPTIONS:
            return True

    def outcome_metrics(
        self, *, expected_after_usd: float, realized_after_usd: float, gross_edge_usd: float
    ) -> Dict[str, Any]:
        return realized_edge_metrics(
            projected_gross_edge_usd=float(gross_edge_usd),
            projected_realized_edge_usd=float(expected_after_usd),
            actual_realized_edge_usd=float(realized_after_usd),
        )

    def submit_to_receipt_ms(self, runtime: Any, pending: Mapping[str, Any]) -> int:
        try:
            submit_ts_s = int(pending.get("ts") or 0)
        except _SAFE_EXCEPTIONS:
            submit_ts_s = 0
        if submit_ts_s <= 0:
            return 0
        latency_ms = int(max(0, int(time.time() * 1000) - int(submit_ts_s) * 1000))
        control = getattr(runtime, "_runtime_control_service", None)
        if control is not None and hasattr(control, "record_submit_to_receipt_latency"):
            control.record_submit_to_receipt_latency(runtime, latency_ms)
        return latency_ms

    @staticmethod
    def update_realized_gas_budget(
        runtime: Any, *, gas_est_wei: int, decoded: Mapping[str, Any]
    ) -> None:
        try:
            runtime._reset_budget_day_if_needed()
            runtime._pending_gas_est_wei = max(
                0, int(runtime._pending_gas_est_wei) - int(gas_est_wei)
            )
            real_gas = int(str(decoded.get("realized_gas_cost_wei") or "0"))
            if real_gas > 0:
                runtime._gas_spent_today_wei += real_gas
        except _SAFE_EXCEPTIONS:
            return

    @staticmethod
    def realized_after_wei(decoded: Mapping[str, Any]) -> int:
        try:
            return int(str(decoded.get("realized_profit_after_gas_wei") or "0"))
        except _SAFE_EXCEPTIONS:
            return 0

    def record_trade_outcome(
        self,
        runtime: Any,
        *,
        status: int,
        realized_after: int,
        expected_after: int,
        amount_in: int,
        latency_ms: int,
        mode: str,
        outcome_truth_ok: bool = True,
        outcome_truth_reason_code: str = "ok",
    ) -> None:
        success = bool(status == 1)
        realized_after_success = int(max(0, realized_after)) if success else 0
        try:
            if success:
                runtime.metrics.succeeded += 1
            else:
                runtime.metrics.failed += 1
        except _SAFE_EXCEPTIONS:
            pass
        if bool(outcome_truth_ok):
            capital_writer = getattr(runtime, "_capital_write_service", None)
            bankroll = getattr(runtime, "_bankroll", None)
            if (
                not bool(
                    capital_writer is not None
                    and bool(getattr(capital_writer, "handles_bankroll_outcome_mutation", False))
                )
                and bankroll is not None
                and hasattr(bankroll, "record_trade")
            ):
                try:
                    bankroll.record_trade(
                        success=success,
                        realized_profit_after_gas_wei=realized_after_success,
                        amount_in_wei=int(amount_in),
                    )
                except _SAFE_EXCEPTIONS:
                    pass
            eff = getattr(runtime, "_eff", None)
            if eff is not None and hasattr(eff, "add"):
                try:
                    eff.add(
                        EfficiencyPoint(
                            ts=int(time.time()),
                            expected_after_costs_wei=int(expected_after),
                            realized_after_gas_wei=realized_after_success,
                            success=success,
                            latency_ms=int(latency_ms),
                        )
                    )
                except _SAFE_EXCEPTIONS:
                    pass
        cb = getattr(runtime, "_cb", None)
        if mode in {"auto", "manual"} and cb is not None and hasattr(cb, "record_result"):
            try:
                cb.record_result(
                    ok=success,
                    reason=(
                        "receipt_success"
                        if success and bool(outcome_truth_ok)
                        else (
                            str(outcome_truth_reason_code or "receipt_revert")
                            if success
                            else "receipt_revert"
                        )
                    ),
                )
            except _SAFE_EXCEPTIONS:
                pass

    def record_capture_outcome(
        self,
        runtime: Any,
        *,
        route_id: str,
        pending: Mapping[str, Any],
        status: int,
        capture_lane_pending: str,
        capture_relay_pending: str,
        expected_after: int,
        realized_after: int,
        submit_to_receipt_ms: int,
    ) -> None:
        telemetry = getattr(runtime, "_capture_telemetry", None)
        if telemetry is None or not hasattr(telemetry, "record"):
            return
        templates = getattr(runtime, "_capture_templates", None)
        template = (
            templates.get(route_id) if templates is not None and hasattr(templates, "get") else {}
        )
        metadata = dict((template or {}).get("metadata") or {})
        realized_i = int(max(0, realized_after)) if status == 1 else 0
        try:
            telemetry.record(
                route_family=str(metadata.get("route_family") or ""),
                venues=list(metadata.get("venues") or []),
                lane=str(capture_lane_pending or "RECEIPT"),
                relay=str(capture_relay_pending or ""),
                rpc=str(
                    runtime.cfg.chain.rpc_send[0]
                    if getattr(runtime.cfg.chain, "rpc_send", None)
                    else ""
                ),
                success=bool(status == 1),
                drop=False,
                revert=bool(status != 1),
                stale=False,
                timeout=False,
                slippage_delta_bps=(
                    float(max(0, expected_after - realized_i))
                    if expected_after > realized_i
                    else 0.0
                ),
                realized_pnl_usd=self._realized_usd_from_wei(realized_i),
                expected_pnl_usd=self._realized_usd_from_wei(int(expected_after)),
                quote_drift_bps=0.0,
                latency_ms=float(submit_to_receipt_ms),
            )
        except _SAFE_EXCEPTIONS:
            return

    def update_decision_learning(
        self,
        runtime: Any,
        *,
        route_id: str,
        rl_state: str,
        rl_action: int,
        amount_in: int,
        expected_after: int,
        realized_after: int,
        status: int,
        tx_hash: str,
        mode: str,
        latency_ms: int,
        submit_to_receipt_ms: int,
        aqe_action: str,
        pending: Mapping[str, Any],
        reward_trace: Mapping[str, Any],
    ) -> None:
        decision = getattr(runtime, "_decision", None)
        if decision is None or not hasattr(decision, "on_trade_result"):
            return
        resolved_expected_after = self._contract_expected_after_wei(
            pending, int(expected_after or 0)
        )
        try:
            decision.on_trade_result(
                route_id=route_id,
                rl_state=rl_state,
                rl_action_index=int(rl_action),
                amount_in_wei=int(amount_in),
                expected_after_costs_wei=int(resolved_expected_after),
                realized_after_gas_wei=(int(max(0, realized_after)) if status == 1 else 0),
                ok=bool(status == 1),
                tx_hash=tx_hash,
                extra={
                    "mode": mode,
                    "latency_ms": int(latency_ms),
                    "submit_to_receipt_ms": int(submit_to_receipt_ms),
                    "aqe_action": aqe_action,
                    "opportunity_id": str(pending.get("opportunity_id") or ""),
                    "brain": (
                        dict(pending.get("brain") or {})
                        if isinstance(pending.get("brain"), Mapping)
                        else {}
                    ),
                    "aqe_debug": (
                        dict(pending.get("aqe_debug") or {})
                        if isinstance(pending.get("aqe_debug"), Mapping)
                        else {}
                    ),
                    "strategy": str(pending.get("strategy") or ""),
                    "reward_trace": dict(reward_trace or {}),
                },
            )
        except _SAFE_EXCEPTIONS:
            return

    def audit_reward_trace(
        self,
        runtime: Any,
        *,
        tx_hash: str,
        mode: str,
        route_id: str,
        status: int,
        submit_to_receipt_ms: int,
        realized_after: int,
        expected_after: int,
        reward_trace: Mapping[str, Any],
        pending: Mapping[str, Any] | None = None,
    ) -> None:
        cc = getattr(runtime, "_cc", None)
        if cc is None or not hasattr(cc, "audit") or not self._reward_enabled(runtime):
            return
        resolved_expected_after = self._contract_expected_after_wei(
            pending or {}, int(expected_after or 0)
        )
        try:
            cc.audit.append(
                "trade_outcome",
                {
                    "tx_hash": str(tx_hash),
                    "mode": str(mode),
                    "route_id": str(route_id),
                    "ok": bool(status == 1),
                    "submit_to_receipt_ms": int(submit_to_receipt_ms),
                    "realized_after_gas_wei": str(
                        int(max(0, realized_after)) if status == 1 else 0
                    ),
                    "expected_after_costs_wei": str(int(resolved_expected_after)),
                    "reward_trace": dict(reward_trace or {}),
                    "profitability_chain": self._settlement_profitability_chain(
                        pending=dict(pending or {}),
                        status=int(status),
                        expected_after=int(expected_after),
                        realized_after=int(realized_after),
                    ),
                    "terminal_profitability_authority": self._terminal_profitability_authority(
                        pending or {}
                    ),
                    "terminal_profitability": (
                        dict(
                            (
                                self._terminal_profitability_authority(pending or {}).get(
                                    "profitability"
                                )
                                or {}
                            )
                        )
                        if isinstance(
                            self._terminal_profitability_authority(pending or {}).get(
                                "profitability"
                            ),
                            Mapping,
                        )
                        else {}
                    ),
                    "capital_admission": self._capital_admission(pending or {}),
                },
                actor="system",
                reason="receipt",
            )
        except _SAFE_EXCEPTIONS:
            return

    def finalize_replay(
        self,
        runtime: Any,
        *,
        tx_hash: str,
        status: int,
        receipt: Mapping[str, Any],
        decoded: Mapping[str, Any],
        reward_trace: Mapping[str, Any],
    ) -> None:
        replay = getattr(runtime, "_replay", None)
        if replay is None or not hasattr(replay, "finalize") or not str(tx_hash or ""):
            return
        try:
            replay.finalize(
                tx_hash=str(tx_hash),
                status=("settled" if status == 1 else "failed"),
                receipt=dict(receipt or {}),
                decoded_receipt=dict(decoded or {}),
                reward_trace=dict(reward_trace or {}),
            )
        except _SAFE_EXCEPTIONS:
            return

    def persist_execution_outcome(
        self,
        runtime: Any,
        *,
        pending: Dict[str, Any],
        status: int,
        submit_to_receipt_ms: int,
        realized_usd: float,
        expected_usd: float,
        reward_trace: Dict[str, Any],
        capture_lane_pending: str,
    ) -> Dict[str, Any]:
        route_family_pending = str(pending.get("route_family") or "")
        strategy_family_pending = str(pending.get("strategy_family") or "flashloan_atomic")
        gross_usd = float(expected_usd)
        if getattr(runtime, "_telemetry_service", None) is not None:
            runtime._telemetry_service.record_outcome(
                route_family=route_family_pending,
                strategy_family=str(strategy_family_pending),
                projected_realized_edge_usd=float(expected_usd),
                actual_realized_edge_usd=float(realized_usd),
                projected_gross_edge_usd=float(gross_usd),
                ok=bool(status == 1),
                lane=str(capture_lane_pending or ""),
                chain=str(runtime.cfg.chain.name),
                reward_trace=reward_trace,
                false_admission=1.0 if status != 1 else 0.0,
            )
        if getattr(runtime, "_family_scorecards", None) is not None:
            runtime._family_scorecards.observe(
                family=str(strategy_family_pending),
                realized_pnl_usd=float(realized_usd),
                gas_cost_usd=0.0,
                ok=bool(status == 1),
                regime=str(
                    (getattr(runtime, "_market_regime", {}) or {}).get("regime") or "balanced"
                ),
            )
        env = self._capture_envelope(pending)
        if getattr(runtime, "_endpoint_quality", None) is not None:
            ep = self._capture_endpoint_selection(pending)
            runtime._endpoint_quality.observe(
                lane=str(capture_lane_pending or "RECEIPT"),
                endpoint=str(
                    ep.get("endpoint")
                    or (
                        runtime.cfg.chain.rpc_send[0]
                        if getattr(runtime.cfg.chain, "rpc_send", None)
                        else ""
                    )
                ),
                latency_ms=float(submit_to_receipt_ms),
                ok=bool(status == 1),
                timeout=False,
                error=bool(status != 1),
                relay=False,
            )
            if str(capture_lane_pending or ep.get("relay") or ""):
                runtime._endpoint_quality.observe(
                    lane=str(capture_lane_pending or "RECEIPT"),
                    endpoint=str(capture_lane_pending or ep.get("relay") or ""),
                    latency_ms=float(submit_to_receipt_ms),
                    ok=bool(status == 1),
                    timeout=False,
                    error=bool(status != 1),
                    relay=True,
                )
        if getattr(runtime, "_venue_scorecards", None) is not None:
            pair = (
                "/".join(list(env.get("token_path") or [])[:2])
                if env.get("token_path")
                else "unknown"
            )
            lat_cls = latency_class_for(float(submit_to_receipt_ms))
            size_bucket = size_bucket_for(
                float((self._capture_meta(pending).get("size_mult") or 1.0))
                if isinstance(self._capture_meta(pending), dict)
                else 1.0
            )
            for venue in list(env.get("venues") or []):
                runtime._venue_scorecards.observe(
                    pair=pair,
                    size_bucket=size_bucket,
                    latency_class=lat_cls,
                    venue=str(venue),
                    success=bool(status == 1),
                    realized_edge_usd=float(realized_usd),
                )
        if getattr(runtime, "_route_quality", None) is not None:
            rp = self._capture_route_plan(pending)
            split_signature = ",".join(
                f"{str(x.get('venue') or '')}:{round(float(x.get('share') or 0.0), 4)}"
                for x in list(rp.get("split") or [])
                if isinstance(x, dict)
            )
            env_pair = (
                "/".join(list(env.get("token_path") or [])[:2]) if isinstance(env, dict) else ""
            )
            runtime._route_quality.observe(
                route_family=str(route_family_pending),
                venue_subset=[str(v) for v in list(rp.get("selected_venues") or []) if str(v)],
                split_signature=split_signature or "default",
                ok=bool(status == 1),
                realized_edge_usd=float(realized_usd),
                pair=str(env_pair),
                size_bucket=size_bucket_for(
                    float((self._capture_meta(pending).get("size_mult") or 1.0))
                    if isinstance(self._capture_meta(pending), dict)
                    else 1.0
                ),
                latency_class=latency_class_for(float(submit_to_receipt_ms)),
            )
        return {
            "route_family": route_family_pending,
            "strategy_family": strategy_family_pending,
            "realized_usd": realized_usd,
            "expected_usd": expected_usd,
        }

    def update_execution_learning(
        self,
        runtime: Any,
        *,
        pending: Mapping[str, Any],
        status: int,
        realized_usd: float,
        expected_usd: float,
        route_family: str,
        strategy_family: str,
        capture_lane_pending: str,
    ) -> None:
        calibration = getattr(runtime, "_execution_calibration", None)
        if calibration is not None and hasattr(calibration, "observe"):
            try:
                calibration.observe(
                    route_family=str(route_family),
                    lane=str(capture_lane_pending or "RECEIPT"),
                    projected_realized_edge_usd=float(expected_usd),
                    actual_realized_edge_usd=float(realized_usd),
                    predicted_success_probability=float(
                        (
                            (
                                (pending.get("brain") or {}).get("p_success")
                                if isinstance(pending.get("brain"), Mapping)
                                else 0.7
                            )
                            or 0.7
                        )
                    ),
                    actual_success=bool(status == 1),
                    predicted_slippage_usd=0.0,
                    actual_slippage_usd=max(0.0, expected_usd - realized_usd),
                    predicted_interference_probability=0.0,
                    actual_stale=False,
                    regime=str(
                        (getattr(runtime, "_market_regime", {}) or {}).get("regime") or "balanced"
                    ),
                    projected_gross_edge_usd=float(expected_usd),
                )
            except _SAFE_EXCEPTIONS:
                pass
        edge_learning = getattr(runtime, "_edge_learning", None)
        if edge_learning is not None and hasattr(edge_learning, "observe"):
            pred = dict(self._capture_metadata(pending).get("edge_prediction") or {})
            envd = self._capture_envelope(pending)
            if pred and envd:
                telemetry = getattr(runtime, "_capture_telemetry", None)
                try:
                    edge_learning.observe(
                        envelope=type("EnvObj", (), envd)(),
                        regime=str(
                            (getattr(runtime, "_market_regime", {}) or {}).get("regime")
                            or "balanced"
                        ),
                        lane=str(capture_lane_pending or "RECEIPT"),
                        telemetry=(
                            telemetry.combined_feedback(
                                route_family=str(route_family),
                                venues=list(envd.get("venues") or []),
                                lane=str(capture_lane_pending or "RECEIPT"),
                            )
                            if telemetry is not None and hasattr(telemetry, "combined_feedback")
                            else {}
                        ),
                        prediction=pred,
                        actual_success=bool(status == 1),
                        actual_realized_edge_usd=float(realized_usd),
                        actual_competed_out=bool(status != 1 and realized_usd <= 0.0),
                        actual_stale=False,
                        actual_slippage_bias=max(0.0, float(expected_usd) - float(realized_usd)),
                    )
                except _SAFE_EXCEPTIONS:
                    pass

    def observe_settlement_memory(
        self,
        runtime: Any,
        *,
        pending: Mapping[str, Any],
        status: int,
        submit_to_receipt_ms: int,
        realized_usd: float,
        expected_usd: float,
        gas_est_wei: int,
        route_family: str,
        strategy_family: str,
        route_id: str,
        tx_hash: str,
        capture_lane_pending: str,
        capture_relay_pending: str,
    ) -> None:
        env = self._capture_envelope(pending)
        settlement_sync = dict(getattr(runtime, "_last_settlement_sync", {}) or {})
        profitability_chain = self._safe_dict(settlement_sync.get("profitabilityChain"))
        if not profitability_chain:
            profitability_chain = self._settlement_profitability_chain(
                pending=pending,
                status=int(status),
                expected_after=int(round(float(expected_usd) * 1_000_000.0)),
                realized_after=int(round(float(realized_usd) * 1_000_000.0)),
            )
        if getattr(runtime, "_venue_profiles", None) is not None:
            for venue in list(env.get("venues") or []):
                try:
                    runtime._venue_profiles.observe(
                        venue=str(venue),
                        success=bool(status == 1),
                        stale_quote=False,
                        slippage_bias_bps=float(max(0.0, expected_usd - realized_usd)),
                        latency_ms=float(pending.get("latency_ms") or 0.0),
                        route_success_contribution=1.0 if bool(status == 1) else 0.0,
                    )
                except _SAFE_EXCEPTIONS:
                    continue
        if getattr(runtime, "_drawdown_state", None) is not None:
            try:
                venue0 = str((list(env.get("venues") or [""]) or [""])[0])
                runtime._drawdown_state.observe(
                    family=str(strategy_family),
                    route_family=str(route_family),
                    venue=venue0,
                    lane=str(capture_lane_pending or "RECEIPT"),
                    regime=str(
                        (getattr(runtime, "_market_regime", {}) or {}).get("regime") or "balanced"
                    ),
                    realized_pnl_usd=float(realized_usd),
                )
            except _SAFE_EXCEPTIONS:
                pass
        if getattr(runtime, "_kill_switch", None) is not None:
            ep = self._capture_endpoint_selection(pending)
            try:
                venue0 = str((list(env.get("venues") or [""]) or [""])[0])
                runtime._kill_switch.observe_outcome(
                    family=str(strategy_family),
                    route_family=str(route_family),
                    venue=venue0,
                    lane=str(capture_lane_pending or "RECEIPT"),
                    ok=bool(status == 1),
                    expected_edge_usd=float(expected_usd),
                    realized_edge_usd=float(realized_usd),
                    slippage_drift_bps=max(0.0, float(expected_usd) - float(realized_usd)),
                    stale=False,
                    fee_burn_usd=(
                        float(gas_est_wei) / 1_000_000.0
                        if abs(float(gas_est_wei)) > 1000
                        else float(gas_est_wei)
                    ),
                    rpc_pressure=float(ep.get("pressure") or 0.0),
                    chain=str(runtime.cfg.chain.name),
                )
            except _SAFE_EXCEPTIONS:
                pass
        if getattr(runtime, "_risk_memory", None) is not None and not bool(status == 1):
            try:
                runtime._risk_memory.observe_failure(
                    route_family=str(route_family),
                    venue=str((list(env.get("venues") or [""]) or [""])[0]),
                    token_pair="/".join(list(env.get("token_path") or [])[:2]),
                    strategy_family=str(strategy_family),
                    chain=str(runtime.cfg.chain.name),
                    pool_path="|".join(list(env.get("venues") or [])),
                )
            except _SAFE_EXCEPTIONS:
                pass
        if getattr(runtime, "_path_diversity", None) is not None and bool(status == 1):
            try:
                pid = "|".join(
                    [
                        str(env.get("route_family") or ""),
                        str(env.get("route_id") or ""),
                        ",".join(list(env.get("venues") or [])),
                        ",".join(list(env.get("token_path") or [])),
                        str(getattr(runtime.cfg.chain, "chain_id", 0) or 0),
                        str(capture_lane_pending or "RECEIPT"),
                    ]
                )
                runtime._path_diversity.observe(pid)
            except _SAFE_EXCEPTIONS:
                pass
        if getattr(runtime, "_family_covariance", None) is not None:
            try:
                runtime._family_covariance.observe(str(strategy_family), float(realized_usd))
            except _SAFE_EXCEPTIONS:
                pass
        if getattr(runtime, "_lifecycle_memory", None) is not None:
            try:
                runtime._lifecycle_memory.append(
                    family=str(strategy_family),
                    strategy_id=str(route_id),
                    stage=("production" if bool(status == 1) else "degraded"),
                    reason_code=("settled_success" if bool(status == 1) else "settled_failure"),
                    payload={
                        "tx_hash": str(tx_hash),
                        "expected_usd": float(expected_usd),
                        "realized_usd": float(realized_usd),
                        "terminalProfitabilityAuthority": dict(
                            profitability_chain.get("terminalProfitabilityAuthority") or {}
                        ),
                        "terminalProfitability": dict(
                            profitability_chain.get("terminalProfitability") or {}
                        ),
                        "capitalAdmission": dict(profitability_chain.get("capitalAdmission") or {}),
                        "profitabilityChain": dict(profitability_chain),
                    },
                )
            except _SAFE_EXCEPTIONS:
                pass
        if (
            getattr(runtime, "_agent_attribution", None) is not None
            or getattr(runtime, "_agent_weighting", None) is not None
        ):
            hub = dict(getattr(runtime, "_agent_hub_last", {}) or {})
            contribs = []
            for name, signal in dict(hub.get("signals") or {}).items():
                try:
                    confidence = float((hub.get("confidences") or {}).get(name, 0.0) or 0.0)
                    followed = bool(float(signal) >= 0.0 and expected_usd >= 0.0)
                    precision_hit = bool(
                        (float(signal) >= 0.0 and realized_usd >= 0.0)
                        or (float(signal) < 0.0 and realized_usd <= 0.0)
                    )
                    impact = (
                        float(realized_usd) * max(-1.0, min(1.0, float(signal) * confidence)) * 0.2
                    )
                    contrib = {
                        "agent": str(name),
                        "signal": float(signal),
                        "confidence": confidence,
                        "followed": followed,
                        "realized_pnl_impact_usd": float(impact),
                        "precision_hit": precision_hit,
                    }
                    contribs.append(contrib)
                    if getattr(runtime, "_agent_weighting", None) is not None:
                        runtime._agent_weighting.observe(
                            agent=str(name),
                            regime=str(
                                (getattr(runtime, "_market_regime", {}) or {}).get("regime")
                                or "balanced"
                            ),
                            followed=followed,
                            predicted_signal=float(signal),
                            realized_edge_usd=float(realized_usd),
                        )
                except _SAFE_EXCEPTIONS:
                    continue
            if getattr(runtime, "_agent_attribution", None) is not None:
                try:
                    runtime._agent_attribution.append(
                        {
                            "ts": int(time.time()),
                            "opportunity_id": str(pending.get("opportunity_id") or ""),
                            "route_id": str(route_id),
                            "strategy_family": str(strategy_family),
                            "contributors": contribs,
                        }
                    )
                except _SAFE_EXCEPTIONS:
                    pass
        # Agent performance and blockspace are handled by explicit helpers below to keep hooks readable.

    def update_agent_performance(
        self,
        runtime: Any,
        *,
        pending: Mapping[str, Any],
        status: int,
        amount_in: int,
        realized_after: int,
    ) -> None:
        perf = getattr(runtime, "_agent_perf", None)
        if perf is None or not hasattr(perf, "update"):
            return
        try:
            if int(status) == 1 and int(amount_in or 0) > 0:
                reward = float(max(0, realized_after)) / float(int(amount_in))
            elif int(status) != 1:
                reward = -0.0001
            else:
                reward = 0.0
        except _SAFE_EXCEPTIONS:
            reward = 0.0
        try:
            from victor_ai_bot.caq_kds.bus import BUS

            bus = BUS.snapshot()
            regime = (
                str((bus.get("behaveagent") or {}).get("regime_label", "unknown"))
                if isinstance(bus, dict)
                else "unknown"
            )
        except _SAFE_EXCEPTIONS:
            regime = "unknown"
        signals = dict((getattr(runtime, "_agent_hub_last", {}) or {}).get("signals") or {})
        confidences = dict((getattr(runtime, "_agent_hub_last", {}) or {}).get("confidences") or {})
        for name, signal in list(signals.items()):
            try:
                confidence = float(confidences.get(name, 0.5) or 0.5)
                perf.update(
                    agent=str(name),
                    reward=float(reward),
                    regime=str(regime),
                    strategy=str(pending.get("strategy") or ""),
                    contribution=float(max(-1.0, min(1.0, float(signal) * confidence))),
                )
            except _SAFE_EXCEPTIONS:
                continue
        behave = getattr(runtime, "_behave", None)
        if behave is not None and hasattr(behave, "observe_outcome"):
            try:
                behave.observe_outcome(
                    regime_label=str(regime),
                    strategy_type=str(pending.get("strategy_type") or "unknown"),
                    reward=float(reward),
                    ok=bool(int(status) == 1),
                )
            except _SAFE_EXCEPTIONS:
                pass

    def observe_blockspace(
        self, runtime: Any, *, status: int, realized_after: int, decoded: Mapping[str, Any]
    ) -> None:
        blockspace = getattr(runtime, "_blockspace", None)
        if blockspace is None or not hasattr(blockspace, "observe_trade"):
            return
        try:
            gas_cost_wei = int(str(decoded.get("realized_gas_cost_wei") or "0"))
        except _SAFE_EXCEPTIONS:
            gas_cost_wei = 0
        try:
            blockspace.observe_trade(
                ok=bool(status == 1),
                profit_after_gas_wei=int(max(0, realized_after)) if status == 1 else 0,
                gas_cost_wei=int(max(0, gas_cost_wei)),
                builder=str(decoded.get("builder") or ""),
            )
        except _SAFE_EXCEPTIONS:
            return

    def notify_governance(
        self,
        runtime: Any,
        *,
        pending: Mapping[str, Any],
        route_id: str,
        amount_in: int,
        status: int,
        expected_after: int,
        realized_after: int,
    ) -> None:
        superstructure = getattr(runtime, "_super", None)
        if superstructure is None or not hasattr(superstructure, "on_trade_outcome"):
            return
        try:
            superstructure.on_trade_outcome(
                opportunity_id=str(pending.get("opportunity_id") or ""),
                route_id=str(route_id or ""),
                amount_in=int(amount_in or 0),
                ok=bool(status == 1),
                expected_after_costs_wei=int(expected_after or 0),
                realized_after_gas_wei=int(max(0, realized_after)) if status == 1 else 0,
            )
        except _SAFE_EXCEPTIONS:
            return

    def notify_narrative(
        self,
        runtime: Any,
        *,
        tx_hash: str,
        status: int,
        decoded: Mapping[str, Any],
        pending: Mapping[str, Any],
    ) -> None:
        narrative = getattr(runtime, "_inl", None)
        if narrative is None or not hasattr(narrative, "on_receipt"):
            return
        try:
            narrative.on_receipt(
                runtime,
                tx_hash=str(tx_hash),
                status=int(status),
                decoded=dict(decoded or {}),
                pending=dict(pending or {}),
            )
        except _SAFE_EXCEPTIONS:
            return

    def summarize(self, runtime: Any) -> Dict[str, Any]:
        live = (
            runtime.execution_live_state()
            if hasattr(runtime, "execution_live_state")
            else {"items": []}
        )
        items = list((live.get("items") or [])) if isinstance(live, dict) else []
        latest = items[-1] if items else {}
        settlement = dict(getattr(runtime, "_last_settlement_sync", {}) or {})
        reason_code = (
            str(settlement.get("reason_code") or settlement.get("reason") or "")
            if settlement
            else "idle"
        ) or (
            "settled_success"
            if settlement.get("status") == "settled"
            else "settled_failed" if settlement.get("status") == "failed" else "idle"
        )
        degraded = bool(settlement.get("degraded", False) or settlement.get("status") == "failed")
        blocked = bool(settlement.get("blockedAutoTrading", False))
        capital_admission = dict(settlement.get("capitalAdmission") or {})
        if capital_admission:
            capital_admission["stateContract"] = contract_from_surface(
                capital_admission,
                phase="capital_admission",
                default_reason=str(capital_admission.get("reason_code") or "ok"),
                sticky_cycle=True,
                details={
                    "capitalSource": str(capital_admission.get("capital_source") or ""),
                    "requestedNotionalUsd": float(
                        capital_admission.get("requested_notional_usd") or 0.0
                    ),
                },
            )
        settlement_family_info = family_identity(
            str(
                settlement.get("runtimeFamily")
                or settlement.get("family")
                or settlement.get("routeFamily")
                or settlement.get("lastRouteFamily")
                or latest.get("runtimeFamily")
                or latest.get("family")
                or latest.get("routeFamily")
                or "flashloan_atomic"
            )
        )
        settlement_borrowing = dict(settlement.get("borrowing") or {})
        latest_flash = (
            dict(latest.get("flashloan") or {})
            if isinstance(latest.get("flashloan"), dict)
            else {}
        )
        payload = {
            "ok": True,
            "lastTxHash": str(settlement.get("receiptId") or latest.get("txHash") or ""),
            "lastRouteFamily": str(
                settlement.get("routeFamily") or settlement.get("lastRouteFamily") or latest.get("routeFamily") or ""
            ),
            "lastFamily": str(
                settlement.get("family") or settlement_family_info.get("launchFamily") or ""
            ),
            "lastRuntimeFamily": str(
                settlement.get("runtimeFamily") or settlement_family_info.get("runtimeFamily") or ""
            ),
            "lastCapitalFamily": str(
                settlement.get("capitalFamily") or settlement_family_info.get("capitalFamily") or ""
            ),
            "lastDisplayFamily": str(
                settlement.get("displayFamily") or settlement_family_info.get("displayName") or ""
            ),
            "lastFamilyAliases": list(
                settlement.get("familyAliases") or settlement_family_info.get("aliases") or []
            ),
            "lastFamilyIdentity": dict(
                settlement.get("familyIdentity") or settlement_family_info
            ),
            "lastTerminalProfitabilityAuthority": dict(
                settlement.get("terminalProfitabilityAuthority") or {}
            ),
            "lastCapitalAdmission": capital_admission,
            "lastProvider": str(
                settlement_borrowing.get("provider")
                or latest_flash.get("selectedProvider")
                or ""
            ),
            "lastFlashloanFeeWei": int(
                settlement_borrowing.get("flashloanFeeWei")
                or latest_flash.get("flashloanFeeWei")
                or 0
            ),
            "lastBorrowCostUsd": float(
                settlement_borrowing.get("borrowCostUsd")
                or latest_flash.get("borrowCostUsd")
                or 0.0
            ),
            "lastBorrowing": settlement_borrowing,
            "lastLoanSettlement": dict(settlement.get("loanSettlement") or {}),
            "lastLearningSync": dict(settlement.get("learningSync") or {}),
            "lastMemorySync": dict(settlement.get("memorySync") or {}),
            "lastClosedLoop": dict(settlement.get("closedLoop") or {}),
        }
        return attach_state_contract(
            payload,
            phase="settlement",
            reason_code=reason_code,
            degraded=degraded,
            blocked=blocked,
            sticky_cycle=True,
            details={"status": str(settlement.get("status") or "")},
        )
