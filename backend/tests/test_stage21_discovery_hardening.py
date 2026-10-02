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


def test_discovery_load_rehydrates_candidate_token_telemetry(tmp_path):
    p = tmp_path / 'discovery' / 'eth.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    token_a = '0x' + '11' * 20
    token_b = '0x' + '22' * 20
    p.write_text(json.dumps({
        'v3': [{
            'token0': token_a,
            'token1': token_b,
            'fee': 3000,
            'pool': '0x' + '33' * 20,
            'first_seen_block': 1,
            'last_seen_block': 2,
        }]
    }))
    dm = DiscoveryManager(chain_name='eth', data_dir=str(tmp_path))
    telemetry = dm.candidate_token_telemetry(
        SimpleNamespace(chain=SimpleNamespace(token_universe=[token_a]))
    )
    assert token_b in telemetry['observed_not_admitted']
    assert 'univ3_persisted' in telemetry['sources'][token_b]


def test_discovery_load_invalid_json_degrades_safely(tmp_path):
    p = tmp_path / 'discovery' / 'eth.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{not json')
    dm = DiscoveryManager(chain_name='eth', data_dir=str(tmp_path))
    assert dm.v3_pairs() == []



def test_discovery_venue_pairs_expand_from_anchor_to_observed_liquid_token(tmp_path):
    anchor = "0x" + "33" * 20
    discovered = "0x" + "55" * 20
    manager = DiscoveryManager(chain_name="base", data_dir=str(tmp_path))
    cfg = _cfg(chain={"token_universe": [anchor]})

    pairs = manager._supported_discovery_pairs(
        cfg,
        [anchor, discovered],
        [10**18, 10**18],
    )

    assert pairs == [(0, anchor, 1, discovered)]


def test_discovery_venue_pairs_ignore_unanchored_unknown_tokens(tmp_path):
    anchor = "0x" + "33" * 20
    discovered_a = "0x" + "55" * 20
    discovered_b = "0x" + "66" * 20
    manager = DiscoveryManager(chain_name="base", data_dir=str(tmp_path))
    cfg = _cfg(chain={"token_universe": [anchor]})

    pairs = manager._supported_discovery_pairs(
        cfg,
        [discovered_a, discovered_b],
        [10**18, 10**18],
    )

    assert pairs == []


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
async def test_discovery_admits_bounded_v3_pool_event_touching_anchor(tmp_path):
    anchor = '0x' + '33' * 20
    candidate = '0x' + '55' * 20
    pool = '0x' + '66' * 20
    topic = '0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118'

    class _Rpc(_RpcOK):
        async def eth_get_logs(self, *, address, from_block, to_block, topics=None):
            assert address == '0x' + '22' * 20
            assert topics == [topic]
            return [{
                'topics': [
                    topic,
                    '0x' + '00' * 12 + anchor[2:],
                    '0x' + '00' * 12 + candidate[2:],
                    '0x' + '00' * 29 + '0bb8',
                ],
                'data': '0x' + '00' * 32 + '00' * 12 + pool[2:],
            }]

    dm = DiscoveryManager(chain_name='eth', data_dir=str(tmp_path))
    cfg = _cfg(chain={'discovery_pool_max_candidates': 4})
    pairs = await dm.maybe_discover_univ3(_Rpc(), cfg, 100)
    assert any(
        row['token_in'].lower() == anchor.lower()
        and row['token_out'].lower() == candidate.lower()
        and row['fee'] == 3000
        for row in pairs
    )
    telemetry = dm.candidate_token_telemetry(cfg)
    assert candidate.lower() in telemetry['observed_not_admitted']


@pytest.mark.asyncio
async def test_discovery_uses_observed_token_as_bounded_univ3_frontier(tmp_path):
    anchor = "0x" + "33" * 20
    candidate = "0x" + "55" * 20
    event_pool = "0x" + "66" * 20
    frontier_pool = "0x" + "77" * 20
    topic = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"

    class _Rpc(_RpcOK):
        async def eth_get_logs(self, *, address, from_block, to_block, topics=None):
            return [{
                "topics": [
                    topic,
                    "0x" + "00" * 12 + anchor[2:],
                    "0x" + "00" * 12 + candidate[2:],
                    "0x" + "00" * 29 + "0bb8",
                ],
                "data": "0x" + "00" * 32 + "00" * 12 + event_pool[2:],
            }]

        async def eth_call(self, to, data, *, block="latest", from_addr=None):
            self.calls += 1
            return RpcResult(True, result="0x" + "00" * 12 + frontier_pool[2:])

    dm = DiscoveryManager(chain_name="base", data_dir=str(tmp_path))
    cfg = _cfg(
        chain={
            "token_universe": [anchor],
            "discovery_max_calls": 1,
            "discovery_pool_max_candidates": 4,
        }
    )

    pairs = await dm.maybe_discover_univ3(_Rpc(), cfg, 100)

    assert any(
        row["token_in"].lower() == anchor.lower()
        and row["token_out"].lower() == candidate.lower()
        and row["fee"] == 100
        and row["pool"].lower() == frontier_pool.lower()
        for row in pairs
    )
    assert len(pairs) == 2


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
