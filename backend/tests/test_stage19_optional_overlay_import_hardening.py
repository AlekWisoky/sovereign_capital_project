from __future__ import annotations

import importlib

import pytest

from victor_ai_bot import config as config_mod


class _DummyModule:
    DemoSymbol = object()


def test_import_optional_symbol_returns_none_for_missing_optional_relative_module(monkeypatch):
    def fake_import_module(module_name: str, package: str | None = None):
        raise ModuleNotFoundError("missing optional module", name=f"{package}.{module_name.lstrip('.')}" if package else module_name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    assert config_mod._import_optional_symbol(".aqe.fake.module", "DemoSymbol") is None


@pytest.mark.parametrize("missing_name", [".aqe.fake.module", "victor_ai_bot.aqe.fake.module"])
def test_import_optional_symbol_returns_none_for_missing_optional_module_name_forms(monkeypatch, missing_name):
    def fake_import_module(module_name: str, package: str | None = None):
        raise ModuleNotFoundError("missing optional module", name=missing_name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    assert config_mod._import_optional_symbol(".aqe.fake.module", "DemoSymbol") is None


def test_import_optional_symbol_propagates_external_dependency_missing(monkeypatch):
    def fake_import_module(module_name: str, package: str | None = None):
        raise ModuleNotFoundError("missing dependency", name="numpy")

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(ModuleNotFoundError, match="missing dependency"):
        config_mod._import_optional_symbol(".aqe.fake.module", "DemoSymbol")


def test_import_optional_symbol_returns_requested_symbol(monkeypatch):
    def fake_import_module(module_name: str, package: str | None = None):
        return _DummyModule()

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    assert config_mod._import_optional_symbol(".aqe.fake.module", "DemoSymbol") is _DummyModule.DemoSymbol
