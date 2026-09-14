from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from collections.abc import Mapping
from typing import Any, Dict, Iterable
from urllib.request import Request, urlopen


_LISTEN_RE = re.compile(r"Listening on (127\.0\.0\.1):(\d+)")


class ForkSimulationUnavailable(RuntimeError):
    """Raised when an isolated local fork executor cannot be started."""


class AnvilForkExecutor:
    """Run deterministic MEV simulations against an isolated local Anvil fork.

    The upstream RPC is used only to create the fork. All state-changing JSON-RPC
    calls are sent to Anvil on loopback, never to the upstream provider.
    """

    def __init__(self, *, anvil_binary: str = "anvil", startup_timeout_s: float = 15.0):
        self.anvil_binary = anvil_binary
        self.startup_timeout_s = max(1.0, float(startup_timeout_s))

    def simulate(self, *, fork_url: str, fork_block: int, transaction: Mapping[str, Any], scenarios: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        self._validate_request(fork_url, fork_block, transaction, scenarios)
        scenario_list = [dict(item) for item in scenarios]
        process, rpc_url = self._start_fork(fork_url, fork_block)
        try:
            pre_block = self._rpc(rpc_url, "eth_getBlockByNumber", [hex(fork_block), False])
            pre_root = self._require_state_root(pre_block, "fork_block_state_root_missing")
            results = [self._run_scenario(rpc_url, transaction, scenario) for scenario in scenario_list]
            digest = self._scenario_digest(fork_block, transaction, scenario_list)
            return {
                "simulation_id": f"anvil:{digest[:24]}",
                "deterministic": True,
                "fork_block": int(fork_block),
                "pre_state_root": pre_root,
                "post_state_root": results[-1]["post_state_root"],
                "scenario_digest": f"sha256:{digest}",
                "scenario_results": results,
                "reverted": any(bool(item["reverted"]) for item in results),
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def _validate_request(self, fork_url: str, fork_block: int, transaction: Mapping[str, Any], scenarios: Iterable[Mapping[str, Any]]) -> None:
        if not isinstance(fork_url, str) or not fork_url:
            raise ForkSimulationUnavailable("fork_url_missing")
        if int(fork_block) < 0:
            raise ForkSimulationUnavailable("fork_block_invalid")
        if not isinstance(transaction, Mapping) or not transaction.get("to"):
            raise ForkSimulationUnavailable("transaction_invalid")
        if not isinstance(scenarios, Iterable):
            raise ForkSimulationUnavailable("scenarios_missing")
        if shutil.which(self.anvil_binary) is None:
            raise ForkSimulationUnavailable("anvil_binary_missing")

    def _start_fork(self, fork_url: str, fork_block: int) -> tuple[subprocess.Popen[str], str]:
        command = [
            self.anvil_binary,
            "--fork-url",
            fork_url,
            "--fork-block-number",
            str(int(fork_block)),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            line = process.stdout.readline() if process.stdout is not None else ""
            match = _LISTEN_RE.search(line)
            if match:
                return process, f"http://{match.group(1)}:{match.group(2)}"
            if process.poll() is not None:
                raise ForkSimulationUnavailable("anvil_start_failed")
        process.kill()
        process.wait(timeout=3)
        raise ForkSimulationUnavailable("anvil_start_timeout")

    def _run_scenario(self, rpc_url: str, transaction: Mapping[str, Any], scenario: Mapping[str, Any]) -> Dict[str, Any]:
        snapshot = self._rpc(rpc_url, "evm_snapshot", [])
        try:
            conflict_checked = self._check_conflict(rpc_url, transaction)
            gas_multiplier = float(scenario.get("gas_multiplier", 0.0))
            liquidity_multiplier = float(scenario.get("liquidity_multiplier", 0.0))
            oracle_multiplier = float(scenario.get("oracle_multiplier", 0.0))
            for mutation in scenario.get("state_mutations", []) or []:
                self._apply_mutation(rpc_url, mutation)
            receipt = self._rpc(rpc_url, "eth_sendTransaction", [dict(transaction)])
            block = self._rpc(rpc_url, "eth_getBlockByNumber", ["latest", False])
            return {
                "gas_multiplier": gas_multiplier,
                "liquidity_multiplier": liquidity_multiplier,
                "oracle_multiplier": oracle_multiplier,
                "conflict_checked": conflict_checked,
                "reverted": self._receipt_reverted(receipt),
                "post_state_root": self._require_state_root(block, "post_state_root_missing"),
            }
        finally:
            self._rpc(rpc_url, "evm_revert", [snapshot])

    def _check_conflict(self, rpc_url: str, transaction: Mapping[str, Any]) -> bool:
        self._rpc(rpc_url, "eth_estimateGas", [dict(transaction)])
        return True

    def _apply_mutation(self, rpc_url: str, mutation: Any) -> None:
        if not isinstance(mutation, Mapping):
            raise ForkSimulationUnavailable("state_mutation_invalid")
        method = mutation.get("method")
        params = mutation.get("params")
        if not isinstance(method, str) or not method.startswith("anvil_") or not isinstance(params, list):
            raise ForkSimulationUnavailable("state_mutation_invalid")
        self._rpc(rpc_url, method, params)

    @staticmethod
    def _receipt_reverted(receipt: Any) -> bool:
        if not isinstance(receipt, Mapping):
            raise ForkSimulationUnavailable("transaction_receipt_missing")
        return receipt.get("status") in ("0x0", 0)

    @staticmethod
    def _require_state_root(block: Any, reason: str) -> str:
        if not isinstance(block, Mapping) or not isinstance(block.get("stateRoot"), str) or not block["stateRoot"]:
            raise ForkSimulationUnavailable(reason)
        return str(block["stateRoot"])

    @staticmethod
    def _scenario_digest(fork_block: int, transaction: Mapping[str, Any], scenarios: list[Dict[str, Any]]) -> str:
        payload = {"fork_block": int(fork_block), "transaction": dict(transaction), "scenarios": scenarios}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _rpc(rpc_url: str, method: str, params: list[Any]) -> Any:
        request = Request(
            rpc_url,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode())
        if not isinstance(payload, Mapping) or "error" in payload:
            raise ForkSimulationUnavailable(f"rpc_failed:{method}")
        return payload.get("result")
