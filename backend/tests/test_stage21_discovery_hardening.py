import json
from types import SimpleNamespace

import pytest

from victor_ai_bot.discovery import DiscoveryManager
from victor_ai_bot.rpc import RpcResult


class _RpcOK:
    def __init__(self, *, result='0x' + '00' * 12 + '11' * 20):
        self._result = result
        self.calls = 0

    async def eth_call(self, to, data, *, block='latest', from_addr=None):
        self.calls += 1
        return RpcResult(True, result=self._result)


class _RpcBoom:
    async def eth_call(self, to, data, *, block='latest', from_addr=None):
        raise ValueError('rpc_boom')


def _cfg(**overrides):
    chain_defaults = dict(
        univ3_factory='0x' + '22' * 20,
        token_universe=['0x' + '33' * 20, '0x' + '44' * 20],
        discovery_interval_blocks=1,
        discovery_max_calls=2,
        weth='0x' + '33' * 20,
    )
    chain_defaults.update(overrides.pop('chain', {}))
    flags_defaults = {'enable_discovery': True}
    flags_defaults.update(overrides.pop('flags', {}))
    return SimpleNamespace(chain=SimpleNamespace(**chain_defaults), flags=SimpleNamespace(**flags_defaults), **overrides)


def test_discovery_load_ignores_invalid_entries_and_keeps_valid(tmp_path):
    p = tmp_path / 'discovery' / 'eth.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        'v3': [
            {
                'token0': '0x' + '11' * 20,
                'token1': '0x' + '22' * 20,
                'fee': 3000,
                'pool': '0x' + '33' * 20,
                'first_seen_block': 1,
                'last_seen_block': 2,
            },
            {'token0': 'bad'},
            'not-a-dict',
        ]
    }))
    dm = DiscoveryManager(chain_name='eth', data_dir=str(tmp_path))
    pairs = dm.v3_pairs()
    assert len(pairs) == 1
    assert pairs[0]['fee'] == 3000


def test_discovery_load_invalid_json_degrades_safely(tmp_path):
    p = tmp_path / 'discovery' / 'eth.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{not json')
    dm = DiscoveryManager(chain_name='eth', data_dir=str(tmp_path))
    assert dm.v3_pairs() == []


@pytest.mark.asyncio
async def test_discovery_runtime_value_error_degrades_safely(tmp_path):
    dm = DiscoveryManager(chain_name='eth', data_dir=str(tmp_path))
    cfg = _cfg()
    pairs = await dm.maybe_discover_univ3(_RpcBoom(), cfg, 100)
    assert pairs == []


@pytest.mark.asyncio
async def test_discovery_saves_found_pairs(tmp_path):
    dm = DiscoveryManager(chain_name='eth', data_dir=str(tmp_path))
    cfg = _cfg(chain={'discovery_max_calls': 1})
    rpc = _RpcOK()
    pairs = await dm.maybe_discover_univ3(rpc, cfg, 100)
    assert rpc.calls == 1
    assert len(pairs) == 1
    saved = json.loads((tmp_path / 'discovery' / 'eth.json').read_text())
    assert saved['v3']


@pytest.mark.asyncio
async def test_discovery_unexpected_programmer_bug_propagates(tmp_path, monkeypatch):
    import victor_ai_bot.discovery as discovery_mod

    dm = DiscoveryManager(chain_name='eth', data_dir=str(tmp_path))
    cfg = _cfg()

    def _boom(_seed):
        raise KeyError('hash_bug')

    monkeypatch.setattr(discovery_mod, 'stable_hash_int', _boom)
    with pytest.raises(KeyError):
        await dm.maybe_discover_univ3(_RpcOK(), cfg, 100)
