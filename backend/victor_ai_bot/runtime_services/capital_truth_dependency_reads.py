from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class CapitalTruthDependencyReadBundle:
    ledger_tail: list[Dict[str, Any]]
    ledger_balances: Dict[str, Any]
    ledger_account_balances: Dict[str, Dict[str, Any]]
    ledger_accounting: Dict[str, Any]
    ledger_transactions: list[Dict[str, Any]]
    bankroll_history_enabled: bool
    bankroll_history_event: Dict[str, Any]
    treasury_history_enabled: bool
    treasury_history_snapshot: Dict[str, Any]
    internal_prime_history_enabled: bool
    internal_prime_state_history_snapshot: Dict[str, Any]
    capital_event_enabled: bool
    capital_event_bankroll: Dict[str, Any]
    capital_event_treasury: Dict[str, Any]
    capital_event_ledger: Dict[str, Any]
    capital_event_receipt: Dict[str, Any]
    capital_event_internal_prime: Dict[str, Any]


def safe_call(obj: Any, method: str, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if obj is None or not hasattr(obj, method):
        return dict(default or {})
    try:
        raw = getattr(obj, method)()
        return dict(raw or {}) if isinstance(raw, dict) else dict(default or {})
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
        return dict(default or {})


def _chain_name(runtime: Any) -> str:
    cfg = getattr(runtime, "cfg", None)
    chain_cfg = getattr(cfg, "chain", None)
    return str(getattr(chain_cfg, "name", "") or "")


def read_ledger_tail(runtime: Any) -> list[Dict[str, Any]]:
    ledger_state = safe_call(runtime, "ledger_state", default={})
    rows = ledger_state.get("tail") or []
    return [dict(row) for row in rows if isinstance(row, dict)]


def read_ledger_balances(runtime: Any) -> Dict[str, Any]:
    ledger_state = safe_call(runtime, "ledger_state", default={})
    return dict(ledger_state.get("balances") or {})


def read_ledger_account_balances(runtime: Any) -> Dict[str, Dict[str, Any]]:
    ledger_state = safe_call(runtime, "ledger_state", default={})
    raw = dict(ledger_state.get("accountBalances") or {})
    if not raw:
        chain = _chain_name(runtime)
        repo = getattr(runtime, "_ledger_repo", None)
        ledger = getattr(runtime, "_ledger", None)
        try:
            if repo is not None and hasattr(repo, "transaction_balance_report"):
                raw = dict(
                    (repo.transaction_balance_report(chain=chain) or {}).get("accountBalances")
                    or {}
                )
            elif ledger is not None and hasattr(ledger, "balance_report"):
                raw = dict((ledger.balance_report() or {}).get("accountBalances") or {})
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
            raw = {}
    out: Dict[str, Dict[str, Any]] = {}
    for account, balances in raw.items():
        if isinstance(balances, dict):
            out[str(account)] = dict(balances)
    return out


def read_ledger_accounting(runtime: Any) -> Dict[str, Any]:
    ledger_state = safe_call(runtime, "ledger_state", default={})
    payload = dict(ledger_state.get("accounting") or {})
    if not payload:
        chain = _chain_name(runtime)
        repo = getattr(runtime, "_ledger_repo", None)
        ledger = getattr(runtime, "_ledger", None)
        try:
            if repo is not None and hasattr(repo, "transaction_balance_report"):
                payload = dict(
                    (repo.transaction_balance_report(chain=chain) or {}).get("accounting") or {}
                )
            elif ledger is not None and hasattr(ledger, "balance_report"):
                payload = dict((ledger.balance_report() or {}).get("accounting") or {})
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
            payload = {}
    return payload if isinstance(payload, dict) else {}


def read_all_ledger_transactions(runtime: Any) -> list[Dict[str, Any]]:
    chain = _chain_name(runtime)
    repo = getattr(runtime, "_ledger_repo", None)
    ledger = getattr(runtime, "_ledger", None)
    try:
        if repo is not None and hasattr(repo, "all_transactions"):
            rows = repo.all_transactions(chain=chain)
            return [dict(row) for row in rows if isinstance(row, dict)]
        if repo is not None and hasattr(repo, "prime_transactions"):
            rows = repo.prime_transactions(chain=chain)
            return [dict(row) for row in rows if isinstance(row, dict)]
        if ledger is not None and hasattr(ledger, "transactions_all"):
            rows = ledger.transactions_all()
            return [dict(row) for row in rows if isinstance(row, dict)]
        if ledger is not None and hasattr(ledger, "prime_transactions"):
            rows = ledger.prime_transactions()
            return [dict(row) for row in rows if isinstance(row, dict)]
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
        pass
    ledger_state = safe_call(runtime, "ledger_state", default={})
    rows = ledger_state.get("transactions") or []
    return [dict(row) for row in rows if isinstance(row, dict)]


def has_bankroll_history(runtime: Any) -> bool:
    repo = getattr(runtime, "_bankroll_history_repo", None)
    if repo is None:
        bankroll = getattr(runtime, "_bankroll", None)
        repo = getattr(bankroll, "_history_repo", None)
    return bool(repo is not None and hasattr(repo, "latest_event"))


def read_bankroll_history_event(runtime: Any) -> Dict[str, Any]:
    repo = getattr(runtime, "_bankroll_history_repo", None)
    if repo is None:
        bankroll = getattr(runtime, "_bankroll", None)
        repo = getattr(bankroll, "_history_repo", None)
    if repo is None or not hasattr(repo, "latest_event"):
        return {}
    try:
        payload = repo.latest_event()
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def has_treasury_state_history(runtime: Any) -> bool:
    treasury = getattr(runtime, "_treasury", None)
    repo = getattr(treasury, "_state_repo", None)
    return bool(repo is not None and hasattr(repo, "latest"))


def read_treasury_history_snapshot(runtime: Any) -> Dict[str, Any]:
    treasury = getattr(runtime, "_treasury", None)
    repo = getattr(treasury, "_state_repo", None)
    if repo is None or not hasattr(repo, "latest"):
        return {}
    try:
        payload = repo.latest(state_type="capital_snapshot")
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def has_internal_prime_state_history(runtime: Any) -> bool:
    repo = getattr(runtime, "_internal_prime_state_repo", None)
    if repo is None:
        prime = getattr(runtime, "_internal_prime", None)
        repo = getattr(prime, "_state_repo", None)
    return bool(repo is not None and hasattr(repo, "latest"))


def read_internal_prime_state_history_snapshot(runtime: Any) -> Dict[str, Any]:
    repo = getattr(runtime, "_internal_prime_state_repo", None)
    if repo is None:
        prime = getattr(runtime, "_internal_prime", None)
        repo = getattr(prime, "_state_repo", None)
    if repo is None or not hasattr(repo, "latest"):
        return {}
    try:
        payload = repo.latest(state_type="prime_state")
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def has_capital_event_bus(runtime: Any) -> bool:
    repo = getattr(runtime, "_capital_event_repo", None)
    return bool(repo is not None and hasattr(repo, "latest_event"))


def read_capital_event(runtime: Any, *, domain: str) -> Dict[str, Any]:
    repo = getattr(runtime, "_capital_event_repo", None)
    if repo is None or not hasattr(repo, "latest_event"):
        return {}
    try:
        payload = repo.latest_event(domain=str(domain or ""))
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def build_capital_truth_dependency_reads(runtime: Any) -> CapitalTruthDependencyReadBundle:
    return CapitalTruthDependencyReadBundle(
        ledger_tail=read_ledger_tail(runtime),
        ledger_balances=read_ledger_balances(runtime),
        ledger_account_balances=read_ledger_account_balances(runtime),
        ledger_accounting=read_ledger_accounting(runtime),
        ledger_transactions=[
            dict(row)
            for row in read_all_ledger_transactions(runtime)
            if isinstance(row, dict) and str(row.get("tx_type") or "").startswith("prime_loan_")
        ],
        bankroll_history_enabled=has_bankroll_history(runtime),
        bankroll_history_event=read_bankroll_history_event(runtime),
        treasury_history_enabled=has_treasury_state_history(runtime),
        treasury_history_snapshot=read_treasury_history_snapshot(runtime),
        internal_prime_history_enabled=has_internal_prime_state_history(runtime),
        internal_prime_state_history_snapshot=read_internal_prime_state_history_snapshot(runtime),
        capital_event_enabled=has_capital_event_bus(runtime),
        capital_event_bankroll=read_capital_event(runtime, domain="bankroll"),
        capital_event_treasury=read_capital_event(runtime, domain="treasury"),
        capital_event_ledger=read_capital_event(runtime, domain="ledger"),
        capital_event_receipt=read_capital_event(runtime, domain="receipt"),
        capital_event_internal_prime=read_capital_event(runtime, domain="internal_prime"),
    )
