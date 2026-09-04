from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable


@dataclass(frozen=True)
class BorrowingTruth:
    """Canonical borrowing lifecycle attached to one trade outcome."""

    requested_usd: float = 0.0
    authorized_usd: float = 0.0
    deployed_usd: float = 0.0
    settled_usd: float = 0.0
    realized_cost_usd: float = 0.0
    capacity_usd: float = 0.0
    utilization: float = 0.0
    source: str = "unavailable"
    status: str = "unavailable"
    reason_code: str = "borrowing_truth_unavailable"
    loan_id: str = ""

    @property
    def authorized(self) -> bool:
        return self.authorized_usd > 0.0

    @property
    def deployed(self) -> bool:
        return self.deployed_usd > 0.0

    @property
    def settled(self) -> bool:
        return self.settled_usd > 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "requested": self.requested_usd > 0.0,
                "authorized": self.authorized,
                "deployed": self.deployed,
                "settled": self.settled,
            }
        )
        return payload


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _first(mapping: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return default


def _nested(payload: Dict[str, Any], names: Iterable[str]) -> Dict[str, Any]:
    for name in names:
        value = payload.get(name)
        if isinstance(value, dict):
            return dict(value)
    return {}


def _find_first_key(payload: Any, keys: Iterable[str]) -> Any:
    wanted = set(keys)
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in wanted and value not in (None, ""):
                return value
            found = _find_first_key(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_first_key(value, keys)
            if found not in (None, ""):
                return found
    return None


def resolve_borrowing_truth(
    *,
    runtime: Any | None = None,
    pending: Dict[str, Any] | None = None,
    result: Dict[str, Any] | None = None,
    outcome: Dict[str, Any] | None = None,
) -> BorrowingTruth:
    """Resolve requested/authorized/deployed/settled borrowing truth.

    Borrowing is only classified when the trade explicitly carries a borrowing
    source/loan or a borrowing lifecycle object. Ordinary capital admission does
    not become a borrowing event merely because it has a requested notional.
    """
    pending_m = _mapping(pending)
    result_m = _mapping(result)
    outcome_m = _mapping(outcome)

    context = _mapping(pending_m.get("pending_context"))
    capital_admission = _nested(pending_m, ("capital_admission", "capitalAdmission"))
    if not capital_admission:
        capital_admission = _nested(context, ("capital_admission", "capitalAdmission"))
    admission_details = _nested(capital_admission, ("details",))
    if not admission_details:
        admission_details = _nested(context, ("capital", "capital_engine", "capitalEngine"))

    explicit_borrow = _nested(pending_m, ("borrowing_truth", "borrowingTruth", "borrow"))
    if not explicit_borrow:
        explicit_borrow = _nested(result_m, ("borrowing_truth", "borrowingTruth", "borrow"))
    if not explicit_borrow:
        explicit_borrow = _nested(outcome_m, ("borrowing_truth", "borrowingTruth", "borrow"))

    prime_state: Dict[str, Any] = {}
    prime_source = ""
    if runtime is not None and hasattr(runtime, "internal_prime_state"):
        try:
            candidate = runtime.internal_prime_state()
            if isinstance(candidate, dict):
                prime_state = dict(candidate)
                prime_source = "internal_prime_state"
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            prime_state = {}
    if not prime_state:
        prime_state = _nested(context, ("internal_prime", "internalPrime", "prime"))
        if prime_state:
            prime_source = "transaction_context_internal_prime"

    loan_id = str(
        _first(
            explicit_borrow,
            ("loan_id", "loanId"),
            _first(pending_m, ("loan_id", "loanId"), ""),
        )
        or ""
    )
    if not loan_id:
        loan_id = str(
            _find_first_key(capital_admission, ("loan_id", "loanId"))
            or _find_first_key(admission_details, ("loan_id", "loanId"))
            or _find_first_key(context, ("loan_id", "loanId"))
            or ""
        )

    capital_source = str(
        _first(
            explicit_borrow,
            ("source", "capital_source", "capitalSource", "provider"),
            _first(
                admission_details,
                ("capital_source", "capitalSource", "source", "provider"),
                _first(context, ("capital_source", "capitalSource", "source"), ""),
            ),
        )
        or ""
    ).strip().lower()
    source_hint = " ".join(
        [
            capital_source,
            str(pending_m.get("strategy_family") or ""),
            str(pending_m.get("route_family") or ""),
        ]
    )
    borrowing_candidate = bool(explicit_borrow or loan_id) or any(
        token in source_hint for token in ("internal_prime", "prime", "borrow", "flashloan", "flash_loan")
    )

    linked_loan: Dict[str, Any] = {}
    if loan_id and isinstance(prime_state.get("loans"), dict):
        candidate_loan = prime_state["loans"].get(loan_id)
        if isinstance(candidate_loan, dict):
            linked_loan = dict(candidate_loan)
            borrowing_candidate = True

    requested = 0.0
    authorized = 0.0
    if borrowing_candidate:
        requested = _float(
            _first(
                explicit_borrow,
                ("requested_usd", "requestedUsd", "notional_usd", "notionalUsd"),
                _first(
                    admission_details,
                    (
                        "requested_notional_usd",
                        "requestedNotionalUsd",
                        "notional_usd",
                        "notionalUsd",
                    ),
                    _first(linked_loan, ("notional_usd", "notionalUsd"), 0.0),
                ),
            )
        )
        authorized = _float(
            _first(
                explicit_borrow,
                ("authorized_usd", "authorizedUsd"),
                _first(
                    admission_details,
                    (
                        "authorized_notional_usd",
                        "authorizedNotionalUsd",
                        "approved_notional_usd",
                        "approvedNotionalUsd",
                    ),
                    requested
                    if bool(
                        capital_admission.get(
                            "allowed", capital_admission.get("approved", False)
                        )
                    )
                    else 0.0,
                ),
            )
        )

    deployed = _float(
        _first(
            explicit_borrow,
            ("deployed_usd", "deployedUsd", "actual_deployed_usd", "actualDeployedUsd"),
            _first(
                result_m,
                (
                    "borrow_deployed_usd",
                    "borrowDeployedUsd",
                    "deployed_borrow_usd",
                    "deployedBorrowUsd",
                ),
                _first(pending_m, ("borrow_deployed_usd", "borrowDeployedUsd"), 0.0),
            ),
        )
    )
    settled = _float(
        _first(
            explicit_borrow,
            ("settled_usd", "settledUsd", "actual_settled_usd", "actualSettledUsd"),
            _first(
                outcome_m,
                (
                    "borrow_settled_usd",
                    "borrowSettledUsd",
                    "settled_borrow_usd",
                    "settledBorrowUsd",
                ),
                0.0,
            ),
        )
    )
    realized_cost = _float(
        _first(
            explicit_borrow,
            (
                "realized_cost_usd",
                "realizedCostUsd",
                "realized_borrow_cost_usd",
                "realizedBorrowCostUsd",
            ),
            _first(outcome_m, ("realized_borrow_cost_usd", "realizedBorrowCostUsd"), 0.0),
        )
    )

    if linked_loan:
        loan_notional = _float(_first(linked_loan, ("notional_usd", "notionalUsd"), 0.0))
        if requested <= 0.0:
            requested = loan_notional
        if authorized <= 0.0:
            authorized = loan_notional
        status = str(linked_loan.get("status") or "open").strip().lower()
        if deployed <= 0.0 and status in {"open", "settled", "disputed"}:
            deployed = loan_notional
        if settled <= 0.0 and status == "settled":
            settled = loan_notional
        if realized_cost <= 0.0:
            realized_cost = _float(
                _first(linked_loan, ("borrow_cost_usd", "borrowCostUsd"), 0.0)
            )

    capacity = _float(
        _first(
            explicit_borrow,
            ("capacity_usd", "capacityUsd"),
            _first(prime_state, ("capacityUsd", "capacity_usd"), 0.0),
        )
    )
    utilization = _float(
        _first(
            explicit_borrow,
            ("utilization", "prime_utilization", "primeUtilization"),
            _first(prime_state, ("utilization", "primeUtilization"), 0.0),
        )
    )

    if settled > 0.0:
        status = "settled"
        reason = "borrowing_settled"
    elif deployed > 0.0:
        status = "deployed"
        reason = "borrowing_deployed"
    elif authorized > 0.0:
        status = "authorized"
        reason = "borrowing_authorized"
    elif requested > 0.0:
        status = "requested"
        reason = "borrowing_requested"
    else:
        status = "unavailable"
        reason = "borrowing_truth_unavailable"

    source = (
        "explicit_trade_context"
        if explicit_borrow
        else ("internal_prime_loan" if linked_loan else (prime_source if borrowing_candidate else "unavailable"))
    )
    return BorrowingTruth(
        requested_usd=max(0.0, requested),
        authorized_usd=max(0.0, authorized),
        deployed_usd=max(0.0, deployed),
        settled_usd=max(0.0, settled),
        realized_cost_usd=max(0.0, realized_cost),
        capacity_usd=max(0.0, capacity),
        utilization=min(1.0, max(0.0, utilization)),
        source=source,
        status=status,
        reason_code=reason,
        loan_id=loan_id,
    )
