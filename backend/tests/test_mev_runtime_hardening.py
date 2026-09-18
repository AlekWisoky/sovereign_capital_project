import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import victor_ai_bot.aqe.mev.runtime as mev_runtime_module
from victor_ai_bot.aqe.mev.mempool import MempoolMonitor
from victor_ai_bot.aqe.mev.models import MEVConfig, decode_allowlisted_univ3_swap, produce_flash_arb_context_from_router
from victor_ai_bot.aqe.mev.search_engine import MEVSearchEngine, MEVStrategySimulationContextProducer
from victor_ai_bot.aqe.mev.simulator import AnvilForkExecutor, ForkSimulationUnavailable

MEVRuntime = mev_runtime_module.MEVRuntime

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
    txd = {'to': '0x1111111111111111111111111111111111111111', 'from': '0x2222222222222222222222222222222222222222', 'nonce': '0x1', 'value': '0x0', 'gas': '0x5208', 'gasPrice': '0x3b9aca00', 'input': '0x38ed1739'}
    runtime = _runtime(txd=txd)
    monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient(txd))
    monkeypatch.setattr(mev_runtime_module.BUS, 'update', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('ignore me')))
    await runtime._loop()
    st = runtime.state()
    assert st['pending_count'] == 1
    assert st['last_error'] == ''


@pytest.mark.asyncio
async def test_bus_update_programmer_bug_is_not_swallowed(monkeypatch):
    txd = {'to': '0x1111111111111111111111111111111111111111', 'from': '0x2222222222222222222222222222222222222222', 'nonce': '0x1', 'value': '0x0', 'gas': '0x5208', 'gasPrice': '0x3b9aca00', 'input': '0x38ed1739'}
    runtime = _runtime(txd=txd)
    monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient(txd))
    monkeypatch.setattr(mev_runtime_module.BUS, 'update', lambda *args, **kwargs: (_ for _ in ()).throw(NameError('bus bug')))
    with pytest.raises(NameError):
        await runtime._loop()


@pytest.mark.asyncio
async def test_stop_cancels_task_without_swallowing(monkeypatch):
    runtime = _runtime(txd={'to': '0x1'})
    class _FakeTask:
        def __init__(self): self.cancelled = False
        def cancel(self): self.cancelled = True; return True
    runtime._task = _FakeTask()
    await runtime.stop()
    assert runtime._task.cancelled is True


def test_mev_runtime_module_has_no_broad_exception_handlers():
    module = ast.parse((ROOT / 'runtime.py').read_text(encoding='utf-8'))
    broad = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ExceptHandler): continue
        if node.type is None: broad.append('bare except')
        elif isinstance(node.type, ast.Name) and node.type.id == 'Exception': broad.append('except Exception')
    assert broad == []


def test_anvil_cleanup_kills_and_fails_closed_if_forced_wait_times_out():
    class _CleanupProcess:
        def __init__(self): self.terminated = False; self.killed = False; self.wait_calls = 0
        def terminate(self): self.terminated = True
        def kill(self): self.killed = True
        def poll(self): return None
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
    return {'strategy': 'flash_arb', 'tx_hash': tx_hash, 'provider': 'aave', 'borrow_token': address, 'profit_to': address,
            'amount_borrow': 1_000_000, 'expected_profit_raw': 50_000,
            'legs': [{'dex': 'univ3', 'venue': address, 'token_in': address, 'token_out': '0x' + '2' * 40, 'data': '0x01'}],
            'simulation_request': {'fork_url': 'https://example.invalid/rpc', 'fork_block': 123,
                'transaction': {'hash': tx_hash, 'to': address, 'data': '0xabcdef12'},
                'scenarios': [{'gas_multiplier': 1.0, 'liquidity_multiplier': 1.0, 'oracle_multiplier': 1.0,
                    'economic_observation': {'account': address, 'assets': [{'address': 'native', 'decimals': 18, 'price_usd': 2000.0, 'role': 'profit'}]}}]}}


def test_strategy_context_producer_requires_explicit_economic_observation():
    producer = MEVStrategySimulationContextProducer(); tx_hash = '0x' + '1' * 64; context = _strategy_context(tx_hash)
    assert producer.produce(tx_hash=tx_hash, strategy_context=context) is not None
    context['simulation_request']['scenarios'][0].pop('economic_observation')
    assert producer.produce(tx_hash=tx_hash, strategy_context=context) is None


def test_strategy_context_producer_rejects_mismatched_pending_transaction():
    producer = MEVStrategySimulationContextProducer(); context = _strategy_context('0x' + '1' * 64)
    assert producer.produce(tx_hash='0x' + '2' * 64, strategy_context=context) is None


def test_mev_search_consumes_produced_context():
    tx_hash = '0x' + '3' * 64; context = _strategy_context(tx_hash)
    evidence = {'simulation_id': 'sim-1', 'deterministic': True, 'fork_block': 123, 'pre_state_root': '0xpre', 'post_state_root': '0xpost', 'scenario_digest': 'sha256:scenario-1',
                'scenario_results': [{'gas_multiplier': 1.0, 'liquidity_multiplier': 1.0, 'oracle_multiplier': 1.0, 'conflict_checked': True, 'reverted': False}], 'reverted': False,
                'economics': {'simulation_id': 'sim-1', 'scenario_digest': 'sha256:scenario-1', 'expected_realized_profit_usd': 17.5, 'gross_asset_delta_usd': 20.0, 'gas_cost_usd': 2.0, 'borrow_cost_usd': 0.5}}
    class _Executor:
        def simulate(self, **request):
            assert request['transaction']['hash'] == tx_hash; assert request['scenarios'][0]['economic_observation']['assets']; return evidence
    rows = MEVSearchEngine(fork_executor=_Executor()).search(mev_state={'sample_pending': [{'hash': tx_hash, 'to': '0x' + '1' * 40, 'value_wei': 0, 'tags': ['dex_like'], 'sel': '0xabcdef12', 'strategy_context': context}], 'high_risk_ratio': 0.0}, base_opportunities=[])
    assert len(rows) == 1; assert rows[0].expected_profit_usd == 17.5; assert rows[0].metadata['economics_status'] == 'simulation_backed'; assert rows[0].metadata['flash_arb_context']['strategy'] == 'flash_arb'


def test_pending_transaction_without_explicit_context_stays_non_authoritative():
    rows = MEVSearchEngine().search(mev_state={'sample_pending': [{'hash': '0x4', 'to': '0x' + '1' * 40, 'value_wei': 5 * 10**18, 'tags': ['dex_like'], 'sel': '0xabcdef12'}], 'high_risk_ratio': 0.2}, base_opportunities=[])
    assert rows[0].expected_profit_usd == 0.0; assert rows[0].metadata['economics_status'] == 'heuristic_non_authoritative'


ROUTER = '0x0000000000000000000000000000000000000010'
TOKEN_A = '0x0000000000000000000000000000000000000020'
TOKEN_B = '0x0000000000000000000000000000000000000030'
RECIPIENT = '0x0000000000000000000000000000000000000040'
PROFIT_TO = '0x0000000000000000000000000000000000000050'
VENUE_A = '0x0000000000000000000000000000000000000060'
VENUE_B = '0x0000000000000000000000000000000000000070'


def _word(value: int) -> str: return f'{int(value):064x}'

def _address_word(address: str) -> str: return address[2:].rjust(64, '0')

def _swap_tx(*, to: str = ROUTER, tx_hash: str = '0xabc') -> dict:
    payload = ''.join([_address_word(TOKEN_A), _address_word(TOKEN_B), _word(3000), _address_word(RECIPIENT), _word(9999999999), _word(1000), _word(950), _word(0)])
    return {'hash': tx_hash, 'to': to, 'input': '0x414bf389' + payload, 'tags': ['dex_like'], 'sel': '0x414bf389'}


def _base_opportunity():
    return SimpleNamespace(id='opp-1', strategy='two-leg:univ3->univ3', expected_profit_raw='25', route_id='route-1', route=SimpleNamespace(legs=[SimpleNamespace(dex='univ3', venue=VENUE_A, token_in=TOKEN_A, token_out=TOKEN_B, amount_in='1000', min_out='950', data='0x' + '00' * 32), SimpleNamespace(dex='univ3', venue=VENUE_B, token_in=TOKEN_B, token_out=TOKEN_A, amount_in='950', min_out='1005', data='0x' + '00' * 32)]))


def test_decode_allowlisted_univ3_exact_input_single():
    decoded = decode_allowlisted_univ3_swap(_swap_tx(), router=ROUTER)
    assert decoded is not None; assert decoded['token_in'] == TOKEN_A; assert decoded['token_out'] == TOKEN_B; assert decoded['fee'] == 3000; assert decoded['amount_in'] == 1000; assert decoded['amount_out_minimum'] == 950


def test_decode_rejects_non_allowlisted_router_and_unknown_selector():
    assert decode_allowlisted_univ3_swap(_swap_tx(to=VENUE_A), router=ROUTER) is None
    tx = _swap_tx(); tx['input'] = '0xdeadbeef' + tx['input'][10:]
    assert decode_allowlisted_univ3_swap(tx, router=ROUTER) is None


def test_context_uses_existing_two_leg_route_and_requires_explicit_simulation():
    kwargs = {'tx': _swap_tx(), 'router': ROUTER, 'base_opportunities': [_base_opportunity()], 'provider': 'aave', 'profit_to': PROFIT_TO}
    assert produce_flash_arb_context_from_router(**kwargs) is None
    context = produce_flash_arb_context_from_router(**kwargs, simulation_request={'fork_url': 'https://example.invalid/rpc', 'fork_block': 100, 'transaction': {'to': '0x0000000000000000000000000000000000000090', 'data': '0x'}, 'scenarios': [{'gas_multiplier': 1.0, 'liquidity_multiplier': 1.0, 'oracle_multiplier': 1.0, 'economic_observation': {'account': PROFIT_TO, 'assets': [{'address': 'native', 'decimals': 18, 'price_usd': 1.0}]}}]})
    assert context is not None; assert context['strategy'] == 'flash_arb'; assert context['borrow_token'] == TOKEN_A; assert context['amount_borrow'] == 1000; assert context['expected_profit_raw'] == 25; assert len(context['legs']) == 2; assert context['observed_router_call']['fee'] == 3000


def test_pending_router_call_flows_through_search_with_simulation_backed_economics():
    tx = _swap_tx()
    tx['simulation_request'] = {
        'fork_url': 'https://example.invalid/rpc',
        'fork_block': 123,
        'transaction': {'hash': tx['hash'], 'to': tx['to'], 'data': tx['input']},
        'scenarios': [{'gas_multiplier': 1.0, 'liquidity_multiplier': 1.0, 'oracle_multiplier': 1.0,
                       'economic_observation': {'account': PROFIT_TO, 'assets': [{'address': 'native', 'decimals': 18, 'price_usd': 1.0}]}}],
    }

    class _Executor:
        def simulate(self, **request):
            return {'simulation_id': 'router-sim', 'deterministic': True, 'fork_block': 123,
                    'pre_state_root': '0xpre', 'post_state_root': '0xpost', 'scenario_digest': 'sha256:router',
                    'scenario_results': [{'gas_multiplier': 1.0, 'liquidity_multiplier': 1.0, 'oracle_multiplier': 1.0,
                                          'conflict_checked': True, 'reverted': False}], 'reverted': False,
                    'economics': {'simulation_id': 'router-sim', 'scenario_digest': 'sha256:router',
                                  'expected_realized_profit_usd': 17.5, 'gross_asset_delta_usd': 20.0,
                                  'gas_cost_usd': 2.0, 'borrow_cost_usd': 0.5}}

    rows = MEVSearchEngine(fork_executor=_Executor(), router=ROUTER, provider='aave', profit_to=PROFIT_TO).search(
        mev_state={'sample_pending': [tx], 'high_risk_ratio': 0.0},
        base_opportunities=[_base_opportunity()],
    )
    assert len(rows) == 1
    assert rows[0].expected_profit_usd == 17.5
    assert rows[0].metadata['economics_status'] == 'simulation_backed'
    assert rows[0].metadata['flash_arb_context']['source_route_id'] == 'route-1'
    assert rows[0].lifecycle_eligibility == 'observe_only'
    assert rows[0].policy_eligibility == 'observe_only'


def test_arbitrary_router_call_without_explicit_simulation_context_cannot_be_promoted():
    rows = MEVSearchEngine(router=ROUTER, provider='aave', profit_to=PROFIT_TO).search(
        mev_state={'sample_pending': [_swap_tx()], 'high_risk_ratio': 0.0},
        base_opportunities=[_base_opportunity()],
    )
    assert len(rows) == 1
    assert rows[0].expected_profit_usd == 0.0
    assert 'flash_arb_context' not in rows[0].metadata
    assert rows[0].lifecycle_eligibility == 'observe_only'
    assert rows[0].policy_eligibility == 'observe_only'

@pytest.mark.asyncio
async def test_mev_runtime_state_preserves_transaction_context_for_simulation():
    txd = {
        'to': '0x1111111111111111111111111111111111111111',
        'from': '0x2222222222222222222222222222222222222222',
        'nonce': '0x1',
        'value': '0x0',
        'gas': '0x5208',
        'maxFeePerGas': '0x3b9aca00',
        'input': '0xabcdef12',
    }
    runtime = _runtime(txd=txd)
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient(txd))
        await runtime._loop()
    finally:
        monkeypatch.undo()
    row = runtime.state()['sample_pending'][0]
    assert row['input_0x'] == '0xabcdef12'
    assert row['gas'] == int('0x5208', 16)
    assert row['max_fee_per_gas'] == int('0x3b9aca00', 16)


def test_market_price_evidence_uses_explicit_decimals_and_usd_price(monkeypatch):
    from victor_ai_bot.execution_capture import final_quote

    class _Rpc:
        async def eth_call(self, *args, **kwargs):
            return SimpleNamespace(ok=True, result='0x' + (18).to_bytes(32, 'big').hex())

    async def fake_best(*args, **kwargs):
        return (2000.0, 3000, 2_000_000_000)

    monkeypatch.setattr(final_quote, '_best_v3_quote', fake_best)
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            name='ethereum',
            univ3_factory='0x' + '3' * 40,
            univ3_quoter_v2='0x' + '4' * 40,
            usdc='0x' + '5' * 40,
        ),
        execution=SimpleNamespace(usd_stable_preference='usdc'),
    )
    evidence = __import__('asyncio').run(
        final_quote.produce_market_price_evidence(
            _Rpc(),
            cfg=cfg,
            tokens=[('0x' + '1' * 40, 'profit')],
            block_number=123,
        )
    )
    assert evidence['0x' + '1' * 40]['decimals'] == 18
    assert evidence['0x' + '1' * 40]['price_usd'] == 2000.0
    assert evidence['0x' + '1' * 40]['role'] == 'profit'


def test_search_engine_consumes_runtime_supplied_simulation_request(monkeypatch):
    tx_hash = '0x' + '7' * 64
    request = {'fork_url': 'https://example.invalid/rpc', 'fork_block': 123, 'transaction': {'hash': tx_hash, 'to': '0x' + '9' * 40, 'data': '0xabcdef12'}, 'scenarios': []}
    captured = {}

    def fake_producer(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(
        'victor_ai_bot.aqe.mev.search_engine.produce_flash_arb_context_from_router',
        fake_producer,
    )
    engine = MEVSearchEngine(router='0x' + '9' * 40, provider='aave', profit_to='0x' + '1' * 40)
    engine._prepare_pending_tx(
        {
            'hash': tx_hash,
            'to': '0x' + '9' * 40,
            'input_0x': '0xabcdef12',
        },
        [],
        {tx_hash: request},
    )
    assert captured['simulation_request'] == request
    assert captured['tx']['hash'] == tx_hash
