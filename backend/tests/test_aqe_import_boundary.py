from __future__ import annotations

import builtins
from pathlib import Path

import pytest

import victor_ai_bot.aqe as aqe_module


def _exec_aqe_init(custom_import):
    source = Path(aqe_module.__file__).read_text(encoding="utf-8")
    builtins_dict = dict(vars(builtins))
    builtins_dict["__import__"] = custom_import
    glb = {
        "__name__": "victor_ai_bot.aqe",
        "__package__": "victor_ai_bot.aqe",
        "__file__": str(aqe_module.__file__),
        "__builtins__": builtins_dict,
    }
    exec(compile(source, str(aqe_module.__file__), "exec"), glb)
    return glb


def test_aqe_optional_import_failure_degrades_to_none():
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 1 and name == "spread":
            raise ModuleNotFoundError("optional spread unavailable")
        return real_import(name, globals, locals, fromlist, level)

    glb = _exec_aqe_init(fake_import)
    assert glb["SpreadEngine"] is None
    assert glb["SpreadEngineConfig"] is None
    assert glb["SharedFeatureBus"] is None


def test_aqe_runtime_error_during_optional_import_is_not_swallowed():
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 1 and name == "spread":
            raise RuntimeError("unexpected spread import bug")
        return real_import(name, globals, locals, fromlist, level)

    with pytest.raises(RuntimeError, match="unexpected spread import bug"):
        _exec_aqe_init(fake_import)
