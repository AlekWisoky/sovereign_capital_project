from __future__ import annotations

from types import SimpleNamespace

import victor_ai_bot.runtime_legacy as runtime_legacy
import victor_ai_bot.runtime_services.runtime_constructor_facade as constructor_facade


class _RpcManager:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _Metrics:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _DecisionEngine:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _Db:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _Audit:
    def __init__(self, db):
        self.db = db


class _Omar:
    def __init__(self, *, cfg, chain_name):
        self.cfg = cfg
        self.chain_name = chain_name
        self.started = False

    def start(self):
        self.started = True


class _Discovery:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _Breaker:
    @classmethod
    def from_env(cls):
        return cls()


class _Anomaly:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_runtime_bundle_constructor_installs_omar_lifecycle_bridges(monkeypatch, tmp_path):
    """Verify the real RuntimeBundle.__init__ installs the canonical bridges."""
    events: list[str] = []

    monkeypatch.setattr(constructor_facade, "RpcManager", _RpcManager)
    monkeypatch.setattr(constructor_facade, "PerBlockCache", lambda: object())
    monkeypatch.setattr(constructor_facade, "Metrics", _Metrics)
    monkeypatch.setattr(constructor_facade, "PersistenceDB", _Db)
    monkeypatch.setattr(constructor_facade, "SecurityAuditStore", _Audit)
    monkeypatch.setattr(constructor_facade, "DecisionEngine", _DecisionEngine)
    monkeypatch.setattr(constructor_facade, "DiscoveryManager", _Discovery)
    monkeypatch.setattr(constructor_facade, "CircuitBreaker", _Breaker)
    monkeypatch.setattr(constructor_facade, "AnomalyBreaker", _Anomaly)
    monkeypatch.setattr(constructor_facade, "OmarRuntime", _Omar)
    monkeypatch.setattr(constructor_facade, "canonical_data_dir", lambda _: str(tmp_path))

    monkeypatch.setattr(
        constructor_facade,
        "install_canonical_settlement_interface",
        lambda: events.append("settlement_interface"),
    )
    monkeypatch.setattr(
        constructor_facade,
        "install_canonical_settlement_bridge",
        lambda: events.append("settlement_bridge"),
    )
    monkeypatch.setattr(
        constructor_facade,
        "install_production_lineage_bridge",
        lambda: events.append("lineage_bridge"),
    )
    monkeypatch.setattr(
        constructor_facade,
        "install_omar_lifecycle_hooks",
        lambda: events.append("omar_lifecycle"),
    )

    monkeypatch.setattr(runtime_legacy, "initialize_execution_capture_stack", lambda *a, **k: None)
    monkeypatch.setattr(runtime_legacy, "initialize_runtime_institutional_stack", lambda *a, **k: None)
    monkeypatch.setattr(runtime_legacy, "initialize_optional_overlay_runtimes", lambda *a, **k: None)
    monkeypatch.setattr(runtime_legacy, "initialize_execution_support_stack", lambda *a, **k: None)
    monkeypatch.setattr(runtime_legacy, "initialize_optional_family_runtimes", lambda *a, **k: None)

    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            name="ethereum",
            rpc_read="read-rpc",
            rpc_send="send-rpc",
            rpc_private=["private-rpc"],
        ),
        execution=SimpleNamespace(
            gas_mode="standard",
            send_mode="public",
            auto_trading=True,
            brain_mode="off",
        ),
    )

    runtime = runtime_legacy.RuntimeBundle(cfg)

    assert events == [
        "settlement_interface",
        "settlement_bridge",
        "lineage_bridge",
        "omar_lifecycle",
    ]
    assert runtime._omar.chain_name == "ethereum"
    assert runtime._omar.cfg.enabled is False
    assert runtime._omar.started is False
    assert runtime._auto_trading is True
