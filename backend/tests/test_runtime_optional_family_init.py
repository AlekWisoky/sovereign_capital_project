from types import SimpleNamespace

from victor_ai_bot.runtime_services import runtime_optional_family_init as mod


def _cfg(v1_focus="flashloan_atomic", mev_enabled=False, meta_enabled=False):
    return SimpleNamespace(
        chain=SimpleNamespace(name="ethereum", rpc_read=["http://rpc"], rpc_send=["http://send"], ws=["ws://rpc"]),
        execution=SimpleNamespace(
            v1_focus=v1_focus,
            arbitrage=SimpleNamespace(),
            mev=SimpleNamespace(enabled=mev_enabled, ws=[]),
            meta=SimpleNamespace(enabled=meta_enabled),
        ),
    )


def test_optional_family_init_respects_v1_focus_for_arbitrage_and_mev(monkeypatch, tmp_path):
    created = {}

    monkeypatch.setattr(mod, "ArbitrageRuntime", lambda cfg: created.setdefault("arb", object()))
    monkeypatch.setattr(mod, "MEVRuntime", lambda **kwargs: created.setdefault("mev", object()))
    monkeypatch.setattr(mod, "MEVGuard", lambda **kwargs: created.setdefault("guard", object()))
    monkeypatch.setattr(mod, "MetaStrategyRuntime", lambda **kwargs: created.setdefault("meta", object()))
    monkeypatch.setattr(mod, "canonical_data_dir", lambda _: str(tmp_path))

    runtime = SimpleNamespace()
    mod.initialize_optional_family_runtimes(runtime, _cfg(v1_focus="flashloan_atomic", mev_enabled=True, meta_enabled=True), str(tmp_path))
    assert runtime._arbitrage is None
    assert runtime._mev is None
    assert runtime._mev_guard is None
    assert runtime._meta is created["meta"]


def test_optional_family_init_enables_non_v1_families_when_allowed(monkeypatch, tmp_path):
    created = {}

    monkeypatch.setattr(mod, "ArbitrageRuntime", lambda cfg: created.setdefault("arb", object()))
    monkeypatch.setattr(mod, "MEVRuntime", lambda **kwargs: created.setdefault("mev", object()))
    monkeypatch.setattr(mod, "MEVGuard", lambda **kwargs: created.setdefault("guard", object()))
    monkeypatch.setattr(mod, "MetaStrategyRuntime", lambda **kwargs: created.setdefault("meta", object()))
    monkeypatch.setattr(mod, "canonical_data_dir", lambda _: str(tmp_path))

    runtime = SimpleNamespace()
    mod.initialize_optional_family_runtimes(runtime, _cfg(v1_focus="multi_strategy", mev_enabled=True, meta_enabled=True), str(tmp_path))
    assert runtime._arbitrage is created["arb"]
    assert runtime._mev is created["mev"]
    assert runtime._mev_guard is created["guard"]
    assert runtime._meta is created["meta"]
