from __future__ import annotations

import json
from pathlib import Path

import pytest

from victor_ai_bot.caq_kds.rag_context import (
    RagStrategyContextEngine,
    RegimeMemoryItem,
    RegimeMemoryStore,
)


def test_regime_memory_store_skips_invalid_entries_but_loads_valid_ones(tmp_path: Path) -> None:
    store = RegimeMemoryStore(data_dir=str(tmp_path))
    path = Path(store.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '\n'.join(
            [
                json.dumps(
                    {
                        'ts': 1.0,
                        'regime': 'calm',
                        'vol_cluster': 1,
                        's_embed': [1.0, 0.0],
                        'c_embed': [0.0, 1.0],
                        'ok': True,
                        'r_total': 1.25,
                    }
                ),
                '{bad-json',
            ]
        )
    )

    out = store.query(s_embed=[1.0, 0.0], c_embed=[0.0, 1.0], regime='calm', k=3)

    assert len(out) == 1
    assert out[0][1].regime == 'calm'


def test_regime_memory_store_load_degrades_on_invalid_top_level_json(tmp_path: Path) -> None:
    store = RegimeMemoryStore(data_dir=str(tmp_path))
    path = Path(store.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{not-json\n')

    out = store.query(s_embed=[1.0], c_embed=[0.0], regime='calm', k=3)

    assert out == []


def test_regime_memory_store_query_prefers_same_regime(tmp_path: Path) -> None:
    store = RegimeMemoryStore(data_dir=str(tmp_path))
    store._cache = [
        RegimeMemoryItem(
            ts=1.0,
            regime='calm',
            vol_cluster=1,
            s_embed=[1.0, 0.0],
            c_embed=[0.0, 1.0],
            route_id='r1',
            strategy='alpha',
            ok=True,
            r_total=1.0,
            meta={},
        ),
        RegimeMemoryItem(
            ts=1.0,
            regime='stress',
            vol_cluster=1,
            s_embed=[1.0, 0.0],
            c_embed=[0.0, 1.0],
            route_id='r2',
            strategy='beta',
            ok=True,
            r_total=1.0,
            meta={},
        ),
    ]
    store._loaded = True

    out = store.query(s_embed=[1.0, 0.0], c_embed=[0.0, 1.0], regime='calm', k=2)

    assert len(out) == 2
    assert out[0][1].route_id == 'r1'
    assert out[0][0] > out[1][0]


def test_rag_context_attach_context_and_record_outcome_round_trip(tmp_path: Path) -> None:
    engine = RagStrategyContextEngine(data_dir=str(tmp_path))
    # seed memory first so attach_context retrieves examples
    engine.store.append(
        RegimeMemoryItem(
            ts=1.0,
            regime='calm',
            vol_cluster=2,
            s_embed=[1.0, 0.0],
            c_embed=[0.0, 1.0],
            route_id='seed-route',
            strategy='seed-strategy',
            ok=True,
            r_total=0.5,
            meta={},
        )
    )
    state = {
        'S_global': {'embedding': [1.0, 0.0], 'regime': 'calm', 'vol_cluster': 2},
        'C_t': {'embedding': [0.0, 1.0]},
    }

    out = engine.attach_context(state=state)
    engine.record_outcome(
        route_id='r-new',
        strategy='s-new',
        ok=True,
        r_team=0.1,
        r_total=0.2,
        meta={'source': 'test'},
    )

    assert 'Historical_Context' in state
    assert out['examples']
    assert out['examples'][0]['regime'] == 'calm'
    assert Path(engine.store.path).exists()
    lines = [ln for ln in Path(engine.store.path).read_text().splitlines() if ln.strip()]
    assert len(lines) >= 2


def test_regime_memory_store_append_propagates_unexpected_programmer_bug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = RegimeMemoryStore(data_dir=str(tmp_path))

    def bad_to_dict() -> dict:
        raise NameError('programmer bug')

    item = RegimeMemoryItem(
        ts=1.0,
        regime='calm',
        vol_cluster=1,
        s_embed=[1.0],
        c_embed=[0.0],
    )
    monkeypatch.setattr(item, 'to_dict', bad_to_dict)

    with pytest.raises(NameError):
        store.append(item)
