import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import victor_ai_bot.aqe.mev.runtime as mev_runtime_module
from victor_ai_bot.aqe.mev.mempool import MempoolMonitor
from victor_ai_bot.aqe.mev.models import MEVConfig
from victor_ai_bot.aqe.mev.runtime import MEVRuntime
from victor_ai_bot.aqe.mev.search_engine import MEVSearchEngine, MEVStrategySimulationContextProducer
from victor_ai_bot.aqe.mev.simulator import AnvilForkExecutor, ForkSimulationUnavailable

ROOT = Path(__file__).resolve().parents[1] / 'victor_ai_bot' / 'aqe' / 'mev'


class _FakeMonitor:
    def __init__(self, hashes):
        self._hashes = list(hashes)
        self.status = SimpleNamespace(connected=True, ws_url='ws://demo', last_error='')

    async def stop(self):
        return None

    async def iter_hashes(self):
        for item in self._hashes:
            yield item


class _FakeRpcClient:
    def __init__(self, txd):
        self._txd = txd

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get_tx_by_hash(self, tx_hash):
        return dict(self._txd)


def _runtime(*, txd, hashes=None) -> MEVRuntime:
    runtime = MEVRuntime(cfg=MEVConfig(enabled=True, max_pending=4), ws_urls=['ws://demo'], rpc_http_url='http://rpc')
    runtime._monitor = _FakeMonitor(hashes or ['0xabc'])
    return runtime


def test_mempool_monitor_supports_multiple_sources_and_suppresses_duplicates():
    monitor = MempoolMonitor(ws_urls=['ws://one', 'ws://two'], max_queue=4)

    assert monitor.ws_urls == ['ws://one', 'ws://two']
    assert set(monitor.source_status) == {'ws://one', 'ws://two'}

    monitor._enqueue_hash('0xabc', source_url='ws://one')
    monitor._enqueue_hash('0xabc', source_url='ws://two')
    monitor._enqueue_hash('0xdef', source_url='ws://two')

    assert monitor.q.qsize() == 2
    assert monitor.q.get_nowait() == '0xabc'
    assert monitor.q.get_nowait() == '0xdef'


@pytest.mark.asyncio
async def test_parse_failures_are_recorded_and_contained(monkeypatch):
    runtime = _runtime(txd={'to': '0x1', 'nonce': '0xzz', 'input': '0x1234'})
    monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient({'to': '0x1', 'nonce': '0xzz', 'input': '0x1234'}))

    await runtime._loop()

    assert runtime._last_error.startswith('parse_failed:ValueError:')
    assert runtime.state()['pending_count'] == 0


@pytest.mark.asyncio
async def test_bus_update_value_error_is_safely_ignored(monkeypatch):
    txd = {
        'to': '0x1111111111111111111111111111111111111111',
        'from': '0x2222222222222222222222222222222222222222',
        'nonce': '0x1',
        'value': '0x0',
        'gas': '0x5208',
        'gasPrice': '0x3b9aca00',
        'input': '0x38ed1739',
    }
    runtime = _runtime(txd=txd)
    monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient(txd))
    monkeypatch.setattr(mev_runtime_module.BUS, 'update', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('ignore me')))

    await runtime._loop()

    st = runtime.state()
    assert st['pending_count'] == 1
    assert st['last_error'] == ''


@pytest.mark.asyncio
async def test_bus_update_programmer_bug_is_not_swallowed(monkeypatch):
    txd = {
        'to': '0x1111111111111111111111111111111111111111',
        'from': '0x2222222222222222222222222222222222222222',
        'nonce': '0x1',
        'value': '0x0',
        'gas': '0x5208',
        'gasPrice': '0x3b9aca00',
        'input': '0x38ed1739',
    }
    runtime = _runtime(txd=txd)
    monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient(txd))
    monkeypatch.setattr(mev_runtime_module.BUS, 'update', lambda *args, **kwargs: (_ for _ in ()).throw(NameError('bus bug')))

    with pytest.raises(NameError):
        await runtime._loop()


@pytest.mark.asyncio
async def test_stop_cancels_task_without_swallowing(monkeypatch):
    runtime = _runtime(txd={'to': '0x1'})

    class _FakeTask:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True
            return True

    runtime._task = _FakeTask()
    await runtime.stop()
    assert runtime._task.cancelled is True


def test_mev_runtime_module_has_no_broad_exception_handlers():
    module = ast.parse((ROOT / 'runtime.py').read_text(encoding='utf-8'))
    broad = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            broad.append('bare except')
            continue
        if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
            broad.append('except Exception')
    assert broad == []


def test_anvil_cleanup_kills_and_fails_closed_if_forced_wait_times_out():
    class _CleanupProcess:
        def __init__(self):
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def poll(self):
            return None

        def wait(self, *, timeout):
            self.wait_calls += 1
            raise subprocess.TimeoutExpired(cmd='anvil', timeout=timeout)

    process = _CleanupProcess()
    with pytest.raises(ForkSimulationUnavailable, match='anvil_process_cleanup_timeout'):
        AnvilForkExecutor._cleanup_process(process)
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2


def _strategy_context(tx_hash):
    address = '0x' + '1' * 40
    return {
        'strategy': 'flash_arb',
        'tx_hash': tx_hash,
        'provider': 'aave',
        'borrow_token': address,
        'profit_to': address,
        'amount_borrow': 1_000_000,
        'expected_profit_raw': 50_000,
        'legs': [{'dex': 'univ3', 'venue': address, 'token_in': address, 'token_out': '0x' + '2' * 40, 'data': '0x01'}],
        'simulation_request': {
            'fork_url': 'https://example.invalid/rpc',
            'fork_block': 123,
            'transaction': {'hash': tx_hash, 'to': address, 'data': '0xabcdef12'},
            'scenarios': [{
                'gas_multiplier': 1.0,
                'liquidity_multiplier': 1.0,
                'oracle_multiplier': 1.0,
                'economic_observation': {'account': address, 'assets': [{'address': 'native', 'decimals': 18, 'price_usd': 2000.0, 'role': 'profit'}]},
            }],
        },
    }


def test_strategy_context_producer_requires_explicit_economic_observation():
    producer = MEVStrategySimulationContextProducer()
    tx_hash = '0x' + '1' * 64
    context = _strategy_context(tx_hash)
    assert producer.produce(tx_hash=tx_hash, strategy_context=context) is not None
    context['simulation_request']['scenarios'][0].pop('economic_observation')
    assert producer.produce(tx_hash=tx_hash, strategy_context=context) is None


def test_strategy_context_producer_rejects_mismatched_pending_transaction():
    producer = MEVStrategySimulationContextProducer()
    context = _strategy_context('0x' + '1' * 64)
    assert producer.produce(tx_hash='0x' + '2' * 64, strategy_context=context) is None


def test_mev_search_consumes_produced_context():
    tx_hash = '0x' + '3' * 64
    context = _strategy_context(tx_hash)
    evidence = {
        'simulation_id': 'sim-1', 'deterministic': True, 'fork_block': 123,
        'pre_state_root': '0xpre', 'post_state_root': '0xpost', 'scenario_digest': 'sha256:scenario-1',
        'scenario_results': [{'gas_multiplier': 1.0, 'liquidity_multiplier': 1.0, 'oracle_multiplier': 1.0, 'conflict_checked': True, 'reverted': False}],
        'reverted': False,
        'economics': {'simulation_id': 'sim-1', 'scenario_digest': 'sha256:scenario-1', 'expected_realized_profit_usd': 17.5, 'gross_asset_delta_usd': 20.0, 'gas_cost_usd': 2.0, 'borrow_cost_usd': 0.5},
    }

    class _Executor:
        def simulate(self, **request):
            assert request['transaction']['hash'] == tx_hash
            assert request['scenarios'][0]['economic_observation']['assets']
            return evidence

    rows = MEVSearchEngine(fork_executor=_Executor()).search(
        mev_state={'sample_pending': [{'hash': tx_hash, 'to': '0x' + '1' * 40, 'value_wei': 0, 'tags': ['dex_like'], 'sel': '0xabcdef12', 'strategy_context': context}], 'high_risk_ratio': 0.0},
        base_opportunities=[],
    )
    assert len(rows) == 1
    assert rows[0].expected_profit_usd == 17.5
    assert rows[0].metadata['economics_status'] == 'simulation_backed'
    assert rows[0].metadata['flash_arb_context']['strategy'] == 'flash_arb'


def test_pending_transaction_without_explicit_context_stays_non_authoritative():
    rows = MEVSearchEngine().search(
        mev_state={'sample_pending': [{'hash': '0x4', 'to': '0x' + '1' * 40, 'value_wei': 5 * 10**18, 'tags': ['dex_like'], 'sel': '0xabcdef12'}], 'high_risk_ratio': 0.2},
        base_opportunities=[],
    )
    assert rows[0].expected_profit_usd == 0.0
    assert rows[0].metadata['economics_status'] == 'heuristic_non_authoritative'
