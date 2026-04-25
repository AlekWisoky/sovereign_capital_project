from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_constructor_facade import RuntimeConstructorFacade


EXTRACTED_METHODS = {
    '_initialize_runtime_constructor_core',
}


class _Runtime(RuntimeConstructorFacade):
    pass


class _FakeLock:
    pass


class _FakeEvent:
    pass


class _FakeQueue:
    def __init__(self, maxsize: int = 0):
        self.maxsize = maxsize


class _FakeDb:
    def __init__(self, path: str):
        self.path = path


class _FakeSecurityAudit:
    def __init__(self, db):
        self.db = db


class _FakeDecision:
    def __init__(self, *, chain_name: str, data_dir: str, brain_mode: str):
        self.chain_name = chain_name
        self.data_dir = data_dir
        self.brain_mode = brain_mode


class _FakeDiscovery:
    def __init__(self, *, chain_name: str, data_dir: str):
        self.chain_name = chain_name
        self.data_dir = data_dir


class _FakeCircuitBreaker:
    @classmethod
    def from_env(cls):
        return 'cb'


class _FakeAnomaly:
    def __init__(self, *, window: int):
        self.window = window


def test_runtime_bundle_inherits_constructor_facade():
    assert issubclass(RuntimeBundle, RuntimeConstructorFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_initialize_runtime_constructor_core_sets_expected_base_state(monkeypatch, tmp_path):
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.RpcManager',
        lambda **kwargs: ('rpc-manager', kwargs),
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.PerBlockCache',
        lambda: 'cache',
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.Metrics',
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.LatencyProfiler',
        lambda **kwargs: ('lat', kwargs),
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.CircuitBreaker',
        _FakeCircuitBreaker,
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.AnomalyBreaker',
        _FakeAnomaly,
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.PersistenceDB',
        _FakeDb,
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.SecurityAuditStore',
        _FakeSecurityAudit,
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.DecisionEngine',
        _FakeDecision,
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.DiscoveryManager',
        _FakeDiscovery,
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.canonical_data_dir',
        lambda _: str(tmp_path),
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.asyncio.Event',
        _FakeEvent,
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.asyncio.Lock',
        _FakeLock,
    )
    monkeypatch.setattr(
        'victor_ai_bot.runtime_services.runtime_constructor_facade.asyncio.Queue',
        _FakeQueue,
    )

    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            name='ethereum',
            rpc_read='https://read.example',
            rpc_send='https://send.example',
            rpc_private=['https://private.example'],
        ),
        execution=SimpleNamespace(
            gas_mode='aggressive',
            send_mode='private',
            auto_trading=True,
            brain_mode='shadow',
        ),
    )

    runtime = _Runtime()
    runtime._initialize_runtime_constructor_core(cfg)

    assert runtime.cfg is cfg
    assert runtime.rpc_manager[0] == 'rpc-manager'
    assert runtime.cache == 'cache'
    assert runtime.metrics.gas_mode == 'aggressive'
    assert runtime.metrics.send_mode == 'private'
    assert runtime._cb == 'cb'
    assert runtime._anomaly.window == 60
    assert runtime._auto_trading is True
    assert runtime.data_dir == str(tmp_path)
    assert runtime._db.path.endswith('state/xdv_runtime_state.sqlite3')
    assert runtime._security_audit.db is runtime._db
    assert runtime._decision.chain_name == 'ethereum'
    assert runtime._decision.data_dir == str(tmp_path)
    assert runtime._decision.brain_mode == 'shadow'
    assert runtime._discovery.chain_name == 'ethereum'
    assert runtime._discovery.data_dir == str(tmp_path)
    assert runtime._receipt_q.maxsize == 20
    assert runtime._auto_queue == []
    assert runtime._auto_queue_block == 0
    assert runtime._last_submitted_block == 0
