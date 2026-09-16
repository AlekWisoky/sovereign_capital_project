from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...flashloan_providers import is_executable_flashloan_provider, normalize_flashloan_provider


class MEVStrategySimulationContextProducer:
    """Build a simulation-ready MEV context only from explicit strategy inputs.

    This boundary never derives flash-loan terms, route legs, prices, or
    economics from a pending transaction hash. Missing or malformed inputs
    return ``None`` so the downstream simulation gate remains fail-closed.
    """

    @staticmethod
    def _address(value: Any) -> str | None:
        text = str(value or "")
        if len(text) != 42 or not text.startswith("0x"):
            return None
        try:
            int(text[2:], 16)
        except ValueError:
            return None
        return text

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None

    def produce(self, *, tx_hash: str, strategy_context: Any) -> dict[str, Any] | None:
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            return None
        if not isinstance(strategy_context, Mapping):
            return None
        if str(strategy_context.get("strategy") or "") != "flash_arb":
            return None
        if str(strategy_context.get("tx_hash") or tx_hash) != tx_hash:
            return None

        provider = normalize_flashloan_provider(str(strategy_context.get("provider") or ""))
        borrow_token = self._address(strategy_context.get("borrow_token"))
        profit_to = self._address(strategy_context.get("profit_to"))
        amount_borrow = self._positive_int(strategy_context.get("amount_borrow"))
        expected_profit_raw = self._positive_int(strategy_context.get("expected_profit_raw"))
        if not is_executable_flashloan_provider(provider):
            return None
        if not all((borrow_token, profit_to, amount_borrow, expected_profit_raw)):
            return None

        simulation_request = strategy_context.get("simulation_request")
        if not isinstance(simulation_request, Mapping):
            return None
        fork_url = str(simulation_request.get("fork_url") or "")
        transaction = simulation_request.get("transaction")
        scenarios = simulation_request.get("scenarios")
        if not fork_url or not isinstance(transaction, Mapping) or not isinstance(scenarios, list) or not scenarios:
            return None
        if str(transaction.get("hash") or tx_hash) != tx_hash:
            return None
        if not str(transaction.get("to") or "") or not str(transaction.get("data") or "") .startswith("0x"):
            return None
        for scenario in scenarios:
            if not isinstance(scenario, Mapping):
                return None
            if not isinstance(scenario.get("economic_observation"), Mapping):
                return None
            required = ("gas_multiplier", "liquidity_multiplier", "oracle_multiplier")
            if any(key not in scenario for key in required):
                return None

        legs = strategy_context.get("legs")
        if not isinstance(legs, list) or not legs:
            return None
        normalized = {
            "strategy": "flash_arb",
            "tx_hash": tx_hash,
            "provider": provider,
            "borrow_token": borrow_token,
            "profit_to": profit_to,
            "amount_borrow": amount_borrow,
            "expected_profit_raw": expected_profit_raw,
            "legs": [dict(leg) for leg in legs if isinstance(leg, Mapping)],
            "simulation_request": {
                "fork_url": fork_url,
                "fork_block": simulation_request.get("fork_block"),
                "transaction": dict(transaction),
                "scenarios": [dict(scenario) for scenario in scenarios],
            },
        }
        if len(normalized["legs"]) != len(legs):
            return None
        return normalized
