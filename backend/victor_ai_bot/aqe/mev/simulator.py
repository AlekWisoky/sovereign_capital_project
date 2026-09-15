from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from collections.abc import Iterable, Mapping
from typing import Any, Dict
from urllib.request import Request, urlopen


def simulate_bundle(*, expected_profit_usd: float, gas_cost_usd: float, contention_risk: float) -> Dict[str, float | bool]:
    """Legacy planning estimate; never authoritative for MEV admission."""
    gas = float(gas_cost_usd)
    risk = max(0.0, min(1.0, float(contention_risk)))
    realized = max(0.0, float(expected_profit_usd) - gas - float(expected_profit_usd) * risk * 0.35)
    return {'ok': bool(realized > 0.0), 'expected_realized_profit_usd': round(realized, 6), 'contention_penalty_usd': round(float(expected_profit_usd) * risk * 0.35, 6)}


_REQUIRED_EVIDENCE_KEYS = ('simulation_id', 'fork_block', 'pre_state_root', 'post_state_root', 'scenario_digest', 'scenario_results')
_REQUIRED_SCENARIO_KEYS = ('gas_multiplier', 'liquidity_multiplier', 'oracle_multiplier', 'conflict_checked', 'reverted')
_BALANCE_OF_SELECTOR = '70a08231'


def _validate_simulation_scenario(scenario: Any, index: int) -> Dict[str, Any] | None:
    if not isinstance(scenario, Mapping):
        return {'ok': False, 'reason_code': 'simulation_scenario_invalid', 'index': index}
    missing = [key for key in _REQUIRED_SCENARIO_KEYS if key not in scenario]
    if missing:
        return {'ok': False, 'reason_code': 'simulation_scenario_incomplete', 'index': index, 'missing': missing}
    if scenario.get('conflict_checked') is not True or scenario.get('reverted') is True:
        return {'ok': False, 'reason_code': 'simulation_scenario_failed', 'index': index}
    for key in ('gas_multiplier', 'liquidity_multiplier', 'oracle_multiplier'):
        try:
            value = float(scenario[key])
        except (TypeError, ValueError, OverflowError):
            return {'ok': False, 'reason_code': 'simulation_scenario_parameter_invalid', 'index': index, 'field': key}
        if not math.isfinite(value) or value <= 0.0:
            return {'ok': False, 'reason_code': 'simulation_scenario_parameter_invalid', 'index': index, 'field': key}
    return None


def validate_simulation_economics(evidence: Any) -> Dict[str, Any]:
    """Validate simulation economics are explicit, finite, and bound to this simulation."""
    if not isinstance(evidence, Mapping):
        return {'ok': False, 'reason_code': 'simulation_economics_missing'}
    economics = evidence.get('economics')
    if not isinstance(economics, Mapping):
        return {'ok': False, 'reason_code': 'simulation_economics_missing'}
    if str(economics.get('simulation_id') or '') != str(evidence.get('simulation_id') or ''):
        return {'ok': False, 'reason_code': 'simulation_economics_identity_mismatch'}
    if str(economics.get('scenario_digest') or '') != str(evidence.get('scenario_digest') or ''):
        return {'ok': False, 'reason_code': 'simulation_economics_scenario_mismatch'}
    required = ('expected_realized_profit_usd', 'gross_asset_delta_usd', 'gas_cost_usd', 'borrow_cost_usd')
    missing = [key for key in required if economics.get(key) in (None, '')]
    if missing:
        return {'ok': False, 'reason_code': 'simulation_economics_incomplete', 'missing': missing}
    values: Dict[str, float] = {}
    for key in required:
        try:
            value = float(economics[key])
        except (TypeError, ValueError, OverflowError):
            return {'ok': False, 'reason_code': 'simulation_economics_invalid', 'field': key}
        if not math.isfinite(value):
            return {'ok': False, 'reason_code': 'simulation_economics_non_finite', 'field': key}
        if key in ('gas_cost_usd', 'borrow_cost_usd') and value < 0.0:
            return {'ok': False, 'reason_code': 'simulation_economics_negative_cost', 'field': key}
        values[key] = value
    expected = values['gross_asset_delta_usd'] - values['gas_cost_usd'] - values['borrow_cost_usd']
    if abs(expected - values['expected_realized_profit_usd']) > 1e-8:
        return {'ok': False, 'reason_code': 'simulation_economics_not_reconciled'}
    return {'ok': True, 'reason_code': 'simulation_economics_verified', 'expected_realized_profit_usd': values['expected_realized_profit_usd']}


def validate_deterministic_simulation_evidence(evidence: Any) -> Dict[str, Any]:
    """Validate producer-supplied fork evidence without inventing simulation truth."""
    if not isinstance(evidence, Mapping) or not evidence:
        return {'ok': False, 'reason_code': 'simulation_evidence_missing'}
    missing = [key for key in _REQUIRED_EVIDENCE_KEYS if evidence.get(key) in (None, '')]
    if missing:
        return {'ok': False, 'reason_code': 'simulation_evidence_incomplete', 'missing': missing}
    if evidence.get('deterministic') is not True:
        return {'ok': False, 'reason_code': 'simulation_not_deterministic'}
    if evidence.get('reverted') is True:
        return {'ok': False, 'reason_code': 'simulation_reverted'}
    try:
        fork_block = int(evidence['fork_block'])
    except (TypeError, ValueError, OverflowError):
        return {'ok': False, 'reason_code': 'simulation_fork_block_invalid'}
    if fork_block < 0:
        return {'ok': False, 'reason_code': 'simulation_fork_block_invalid'}
    scenarios = evidence.get('scenario_results')
    if not isinstance(scenarios, list) or not scenarios:
        return {'ok': False, 'reason_code': 'simulation_scenarios_missing'}
    for index, scenario in enumerate(scenarios):
        failure = _validate_simulation_scenario(scenario, index)
        if failure is not None:
            return failure
    economics_gate = validate_simulation_economics(evidence)
    if economics_gate.get('ok') is not True:
        return economics_gate
    return {'ok': True, 'reason_code': 'simulation_evidence_verified', 'simulation_id': str(evidence['simulation_id']), 'fork_block': fork_block, 'pre_state_root': str(evidence['pre_state_root']), 'post_state_root': str(evidence['post_state_root']), 'scenario_digest': str(evidence['scenario_digest']), 'scenario_count': len(scenarios), 'expected_realized_profit_usd': economics_gate['expected_realized_profit_usd']}


class ForkSimulationUnavailable(RuntimeError):
    """Raised when an isolated local Anvil fork executor cannot be started."""


class AnvilForkExecutor:
    """Run deterministic MEV simulations against an isolated local Anvil fork."""

    def __init__(self, *, anvil_binary: str = 'anvil', startup_timeout_s: float = 15.0):
        self.anvil_binary = anvil_binary
        self.startup_timeout_s = max(1.0, float(startup_timeout_s))

    def simulate(self, *, fork_url: str, fork_block: int, transaction: Mapping[str, Any], scenarios: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        self._validate_request(fork_url, fork_block, transaction, scenarios)
        scenario_list = [dict(item) for item in scenarios]
        process, rpc_url = self._start_fork(fork_url, fork_block)
        try:
            pre_block = self._rpc(rpc_url, 'eth_getBlockByNumber', [hex(fork_block), False])
            pre_root = self._require_state_root(pre_block, 'fork_block_state_root_missing')
            results = [self._run_scenario(rpc_url, transaction, scenario) for scenario in scenario_list]
            digest = self._scenario_digest(fork_block, transaction, scenario_list)
            economics = results[-1].get('economics')
            simulation_id = f'anvil:{digest[:24]}'
            if isinstance(economics, Mapping):
                economics = dict(economics, simulation_id=simulation_id, scenario_digest=f'sha256:{digest}')
            return {'simulation_id': simulation_id, 'deterministic': True, 'fork_block': int(fork_block), 'pre_state_root': pre_root, 'post_state_root': results[-1]['post_state_root'], 'scenario_digest': f'sha256:{digest}', 'scenario_results': results, 'economics': economics, 'reverted': any(bool(item['reverted']) for item in results)}
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def _validate_request(self, fork_url: str, fork_block: int, transaction: Mapping[str, Any], scenarios: Iterable[Mapping[str, Any]]) -> None:
        self._validate_fork_url(fork_url)
        self._validate_fork_block(fork_block)
        self._validate_transaction(transaction)
        self._validate_scenarios(scenarios)
        self._validate_anvil_binary()

    @staticmethod
    def _validate_fork_url(fork_url: str) -> None:
        if not isinstance(fork_url, str) or not fork_url:
            raise ForkSimulationUnavailable('fork_url_missing')

    @staticmethod
    def _validate_fork_block(fork_block: int) -> None:
        if int(fork_block) < 0:
            raise ForkSimulationUnavailable('fork_block_invalid')

    @staticmethod
    def _validate_transaction(transaction: Mapping[str, Any]) -> None:
        if not isinstance(transaction, Mapping) or not transaction.get('to'):
            raise ForkSimulationUnavailable('transaction_invalid')

    @staticmethod
    def _validate_scenarios(scenarios: Iterable[Mapping[str, Any]]) -> None:
        if not isinstance(scenarios, Iterable):
            raise ForkSimulationUnavailable('scenarios_missing')

    def _validate_anvil_binary(self) -> None:
        if shutil.which(self.anvil_binary) is None:
            raise ForkSimulationUnavailable('anvil_binary_missing')

    def _start_fork(self, fork_url: str, fork_block: int) -> tuple[subprocess.Popen[str], str]:
        command = [self.anvil_binary, '--fork-url', fork_url, '--fork-block-number', str(int(fork_block)), '--host', '127.0.0.1', '--port', '0']
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            line = process.stdout.readline() if process.stdout is not None else ''
            match = re.search(r'Listening on (127[.]0[.]0[.]1):(\\d+)', line)
            if match:
                return process, f'http://{match.group(1)}:{match.group(2)}'
            if process.poll() is not None:
                raise ForkSimulationUnavailable('anvil_start_failed')
        process.kill()
        process.wait(timeout=3)
        raise ForkSimulationUnavailable('anvil_start_timeout')

    def _run_scenario(self, rpc_url: str, transaction: Mapping[str, Any], scenario: Mapping[str, Any]) -> Dict[str, Any]:
        snapshot = self._rpc(rpc_url, 'evm_snapshot', [])
        observation = scenario.get('economic_observation')
        if not isinstance(observation, Mapping):
            raise ForkSimulationUnavailable('economic_observation_missing')
        try:
            before = self._capture_economic_balances(rpc_url, observation)
            conflict_checked = self._check_conflict(rpc_url, transaction)
            gas_multiplier = float(scenario.get('gas_multiplier', 0.0))
            liquidity_multiplier = float(scenario.get('liquidity_multiplier', 0.0))
            oracle_multiplier = float(scenario.get('oracle_multiplier', 0.0))
            for mutation in scenario.get('state_mutations', []) or []:
                self._apply_mutation(rpc_url, mutation)
            tx_hash = self._rpc(rpc_url, 'eth_sendTransaction', [dict(transaction)])
            receipt = self._rpc(rpc_url, 'eth_getTransactionReceipt', [tx_hash])
            block = self._rpc(rpc_url, 'eth_getBlockByNumber', ['latest', False])
            reverted = self._receipt_reverted(receipt)
            if reverted:
                raise ForkSimulationUnavailable('simulation_transaction_reverted')
            after = self._capture_economic_balances(rpc_url, observation)
            economics = self._derive_economics(observation, before, after, receipt)
            return {'gas_multiplier': gas_multiplier, 'liquidity_multiplier': liquidity_multiplier, 'oracle_multiplier': oracle_multiplier, 'conflict_checked': conflict_checked, 'reverted': False, 'post_state_root': self._require_state_root(block, 'post_state_root_missing'), 'economics': economics}
        finally:
            self._rpc(rpc_url, 'evm_revert', [snapshot])

    def _capture_economic_balances(self, rpc_url: str, observation: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        account = str(observation.get('account') or '')
        if not re.fullmatch(r'0x[0-9a-fA-F]{40}', account):
            raise ForkSimulationUnavailable('economic_account_invalid')
        assets = observation.get('assets')
        if not isinstance(assets, list) or not assets:
            raise ForkSimulationUnavailable('economic_assets_missing')
        out: Dict[str, Dict[str, Any]] = {}
        for item in assets:
            if not isinstance(item, Mapping):
                raise ForkSimulationUnavailable('economic_asset_invalid')
            address = str(item.get('address') or 'native')
            key = address.lower()
            if key in out:
                raise ForkSimulationUnavailable('economic_asset_duplicate')
            try:
                decimals = int(item.get('decimals'))
                price_usd = float(item.get('price_usd'))
            except (TypeError, ValueError, OverflowError):
                raise ForkSimulationUnavailable('economic_asset_value_invalid') from None
            if decimals < 0 or decimals > 255 or not math.isfinite(price_usd) or price_usd <= 0.0:
                raise ForkSimulationUnavailable('economic_asset_value_invalid')
            if address == 'native':
                raw = self._rpc(rpc_url, 'eth_getBalance', [account, 'latest'])
            else:
                if not re.fullmatch(r'0x[0-9a-fA-F]{40}', address):
                    raise ForkSimulationUnavailable('economic_token_invalid')
                data = '0x' + _BALANCE_OF_SELECTOR + account[2:].lower().rjust(64, '0')
                raw = self._rpc(rpc_url, 'eth_call', [{'to': address, 'data': data}, 'latest'])
            try:
                balance = int(str(raw), 16)
            except (TypeError, ValueError):
                raise ForkSimulationUnavailable('economic_balance_invalid') from None
            out[key] = {'address': address, 'decimals': decimals, 'price_usd': price_usd, 'role': str(item.get('role') or ''), 'balance': balance}
        return out

    @staticmethod
    def _derive_economics(observation: Mapping[str, Any], before: Mapping[str, Mapping[str, Any]], after: Mapping[str, Mapping[str, Any]], receipt: Mapping[str, Any]) -> Dict[str, Any]:
        try:
            gas_used = int(str(receipt.get('gasUsed')), 16)
            gas_price = int(str(receipt.get('effectiveGasPrice')), 16)
        except (AttributeError, TypeError, ValueError):
            raise ForkSimulationUnavailable('economic_gas_receipt_invalid') from None
        native_price: float | None = None
        for item in before.values():
            if str(item.get('address')) == 'native':
                native_price = float(item.get('price_usd') or 0.0)
                break
        if native_price is None or not math.isfinite(native_price) or native_price <= 0.0:
            raise ForkSimulationUnavailable('economic_native_price_missing')
        gas_cost_usd = (gas_used * gas_price / 10**18) * native_price
        gross = 0.0
        for key, pre in before.items():
            post = after.get(key)
            if not isinstance(post, Mapping) or pre.get('role') != post.get('role') or float(pre.get('price_usd') or 0.0) != float(post.get('price_usd') or 0.0):
                raise ForkSimulationUnavailable('economic_observation_mismatch')
            price = float(pre['price_usd'])
            delta = int(post['balance']) - int(pre['balance'])
            role = str(pre.get('role') or '')
            if role == 'profit':
                if delta < 0:
                    raise ForkSimulationUnavailable('economic_profit_delta_negative')
                value = (delta / (10 ** int(pre['decimals']))) * price
                if str(pre['address']) == 'native':
                    value += gas_cost_usd
                gross += value
            elif role == 'cost':
                if delta > 0:
                    raise ForkSimulationUnavailable('economic_cost_delta_positive')
                value = (delta / (10 ** int(pre['decimals']))) * price
                if str(pre['address']) == 'native':
                    value += gas_cost_usd
                gross += value
            else:
                raise ForkSimulationUnavailable('economic_asset_role_missing')
        borrow_cost_usd = float(observation.get('borrow_cost_usd') or 0.0)
        if not math.isfinite(borrow_cost_usd) or borrow_cost_usd < 0.0:
            raise ForkSimulationUnavailable('economic_borrow_cost_invalid')
        expected = gross - gas_cost_usd - borrow_cost_usd
        if not all(math.isfinite(value) for value in (gross, gas_cost_usd, borrow_cost_usd, expected)):
            raise ForkSimulationUnavailable('economic_non_finite')
        return {'expected_realized_profit_usd': round(expected, 8), 'gross_asset_delta_usd': round(gross, 8), 'gas_cost_usd': round(gas_cost_usd, 8), 'borrow_cost_usd': round(borrow_cost_usd, 8)}

    def _check_conflict(self, rpc_url: str, transaction: Mapping[str, Any]) -> bool:
        self._rpc(rpc_url, 'eth_estimateGas', [dict(transaction)])
        return True

    def _apply_mutation(self, rpc_url: str, mutation: Any) -> None:
        if not isinstance(mutation, Mapping):
            raise ForkSimulationUnavailable('state_mutation_invalid')
        method = mutation.get('method')
        params = mutation.get('params')
        if not isinstance(method, str) or not method.startswith('anvil_') or not isinstance(params, list):
            raise ForkSimulationUnavailable('state_mutation_invalid')
        self._rpc(rpc_url, method, params)

    @staticmethod
    def _receipt_reverted(receipt: Any) -> bool:
        if not isinstance(receipt, Mapping):
            raise ForkSimulationUnavailable('transaction_receipt_missing')
        return receipt.get('status') in ('0x0', 0)

    @staticmethod
    def _require_state_root(block: Any, reason: str) -> str:
        if not isinstance(block, Mapping) or not isinstance(block.get('stateRoot'), str) or not block['stateRoot']:
            raise ForkSimulationUnavailable(reason)
        return str(block['stateRoot'])

    @staticmethod
    def _scenario_digest(fork_block: int, transaction: Mapping[str, Any], scenarios: list[Dict[str, Any]]) -> str:
        payload = {'fork_block': int(fork_block), 'transaction': dict(transaction), 'scenarios': scenarios}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    @staticmethod
    def _rpc(rpc_url: str, method: str, params: list[Any]) -> Any:
        request = Request(rpc_url, data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode())
        if not isinstance(payload, Mapping) or 'error' in payload:
            raise ForkSimulationUnavailable(f'rpc_failed:{method}')
        return payload.get('result')
