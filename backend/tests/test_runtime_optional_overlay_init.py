from types import SimpleNamespace

from victor_ai_bot.runtime_services import runtime_optional_overlay_init as mod


def _cfg(super_enabled=True, fioa_enabled=True, inl_enabled=True):
    return SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        execution=SimpleNamespace(
            superstructure=SimpleNamespace(enabled=super_enabled),
            fioa=SimpleNamespace(enabled=fioa_enabled),
            llm_inl=SimpleNamespace(enabled=inl_enabled),
        ),
    )


def test_optional_overlay_init_wires_superstructure_into_fioa_and_inl(monkeypatch, tmp_path):
    created = {}

    def _super(**kwargs):
        created["super"] = SimpleNamespace(kwargs=kwargs)
        return created["super"]

    def _fioa(**kwargs):
        created["fioa"] = SimpleNamespace(kwargs=kwargs)
        return created["fioa"]

    def _inl(**kwargs):
        created["inl"] = SimpleNamespace(kwargs=kwargs)
        return created["inl"]

    monkeypatch.setattr(mod, "SuperstructureRuntime", _super)
    monkeypatch.setattr(mod, "FIOARuntime", _fioa)
    monkeypatch.setattr(mod, "LLMINLRuntime", _inl)

    runtime = SimpleNamespace()
    mod.initialize_optional_overlay_runtimes(runtime, _cfg(), str(tmp_path))

    assert runtime._super is created["super"]
    assert runtime._fioa is created["fioa"]
    assert runtime._inl is created["inl"]
    assert created["fioa"].kwargs["superstructure"] is created["super"]
    assert created["inl"].kwargs["fioa"] is created["fioa"]


def test_optional_overlay_init_degrades_to_none_on_local_runtime_error(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "SuperstructureRuntime", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "FIOARuntime", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "LLMINLRuntime", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    runtime = SimpleNamespace(_super="sentinel", _fioa="sentinel", _inl="sentinel")
    mod.initialize_optional_overlay_runtimes(runtime, _cfg(), str(tmp_path))

    assert runtime._super is None
    assert runtime._fioa is None
    assert runtime._inl is None
