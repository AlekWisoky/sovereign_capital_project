from __future__ import annotations

"""Exchange connector interfaces.

This layer is strictly *additive*. It is intended to normalize CEX market-data
feeds and order/position APIs without changing the existing core execution
engine.

Live trading must be explicitly enabled via config; otherwise connectors should
operate in quote-only mode.
"""

from dataclasses import dataclass
import importlib
from typing import Any, Dict, List, Optional, Protocol, Type


class ExchangeConnector(Protocol):
    name: str

    def connect(self) -> None: ...
    def subscribe_orderbook(self, symbol: str) -> None: ...
    def subscribe_funding(self, symbol: str) -> None: ...
    def place_order(self, symbol: str, side: str, qty: float, price: Optional[float] = None, *, reduce_only: bool = False) -> Dict[str, Any]: ...
    def cancel_order(self, order_id: str) -> bool: ...
    def get_balance(self) -> Dict[str, float]: ...
    def get_positions(self) -> List[Dict[str, Any]]: ...


@dataclass
class ConnectorConfig:
    name: str
    enable_trading: bool = False
    meta: Dict[str, Any] | None = None


_CCXT_OPTIONAL_IMPORT_EXCEPTIONS = (ImportError,)
_CCXT_CONNECT_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_CCXT_OPERATION_EXCEPTIONS = (AttributeError, TypeError, ValueError, KeyError, RuntimeError, OSError)
_CCXT_FLOAT_COERCE_EXCEPTIONS = (TypeError, ValueError)


def _ccxt_safe_operation_exceptions(exchange: Any) -> tuple[type[BaseException], ...]:
    """Return built-in plus known CCXT exception types for safe degradation.

    This keeps optional integration behavior non-fatal without swallowing
    arbitrary programmer bugs raised by local code.
    """

    exc_types: list[type[BaseException]] = list(_CCXT_OPERATION_EXCEPTIONS)
    module_name = getattr(type(exchange), "__module__", "")
    if module_name:
        try:
            module = importlib.import_module(module_name)
        except (ImportError, AttributeError, ValueError):
            module = None
        if module is not None:
            for name in ("BaseError", "ExchangeError", "NetworkError", "NotSupported"):
                candidate = getattr(module, name, None)
                if isinstance(candidate, type) and issubclass(candidate, BaseException):
                    exc_types.append(candidate)
    return tuple(dict.fromkeys(exc_types))


class QuoteOnlyExchangeConnector:
    """Wrapper that enforces quote-only behavior."""

    def __init__(self, inner: ExchangeConnector):
        self.inner = inner
        self.name = getattr(inner, "name", "")

    def connect(self) -> None:
        return self.inner.connect()

    def subscribe_orderbook(self, symbol: str) -> None:
        return self.inner.subscribe_orderbook(symbol)

    def subscribe_funding(self, symbol: str) -> None:
        return self.inner.subscribe_funding(symbol)

    def place_order(self, *args, **kwargs):
        raise RuntimeError("quote_only:place_order disabled")

    def cancel_order(self, *args, **kwargs):
        raise RuntimeError("quote_only:cancel_order disabled")

    def get_balance(self) -> Dict[str, float]:
        return self.inner.get_balance()

    def get_positions(self) -> List[Dict[str, Any]]:
        return self.inner.get_positions()


class CCXTConnector:
    """Optional CCXT-backed connector.

    This adapter is only usable when `ccxt` is installed.
    """

    def __init__(self, *, exchange_id: str, enable_trading: bool = False, ccxt_kwargs: Optional[Dict[str, Any]] = None):
        self.name = str(exchange_id)
        self.enable_trading = bool(enable_trading)
        self.ccxt_kwargs = dict(ccxt_kwargs or {})
        self._ex = None

    def connect(self) -> None:
        try:
            import ccxt  # type: ignore
        except _CCXT_OPTIONAL_IMPORT_EXCEPTIONS as e:  # pragma: no cover
            raise RuntimeError(f"ccxt not installed: {e}")
        cls = getattr(ccxt, self.name, None)
        if cls is None:
            raise RuntimeError(f"unknown ccxt exchange_id: {self.name}")
        try:
            self._ex = cls(self.ccxt_kwargs)
        except _CCXT_CONNECT_EXCEPTIONS as e:
            raise RuntimeError(f"ccxt connector init failed: {e}") from e

    def subscribe_orderbook(self, symbol: str) -> None:
        # ccxt.pro would be required for websocket streaming; we provide a placeholder.
        return None

    def subscribe_funding(self, symbol: str) -> None:
        return None

    def place_order(self, symbol: str, side: str, qty: float, price: Optional[float] = None, *, reduce_only: bool = False) -> Dict[str, Any]:
        if not self.enable_trading:
            raise RuntimeError("ccxt trading disabled")
        if self._ex is None:
            raise RuntimeError("not connected")
        typ = "market" if price is None else "limit"
        params: Dict[str, Any] = {}
        if reduce_only:
            params["reduceOnly"] = True
        return dict(self._ex.create_order(symbol, typ, side, qty, price, params))

    def cancel_order(self, order_id: str) -> bool:
        if not self.enable_trading:
            raise RuntimeError("ccxt trading disabled")
        if self._ex is None:
            raise RuntimeError("not connected")
        try:
            self._ex.cancel_order(order_id)
            return True
        except _ccxt_safe_operation_exceptions(self._ex):
            return False

    def get_balance(self) -> Dict[str, float]:
        if self._ex is None:
            return {}
        try:
            b = self._ex.fetch_balance()
            free = b.get("free") or {}
            out: Dict[str, float] = {}
            for k, v in free.items():
                try:
                    out[str(k)] = float(v)
                except _CCXT_FLOAT_COERCE_EXCEPTIONS:
                    continue
            return out
        except _ccxt_safe_operation_exceptions(self._ex):
            return {}

    def get_positions(self) -> List[Dict[str, Any]]:
        if self._ex is None:
            return []
        if not hasattr(self._ex, "fetch_positions"):
            return []
        try:
            return list(self._ex.fetch_positions())
        except _ccxt_safe_operation_exceptions(self._ex):
            return []
