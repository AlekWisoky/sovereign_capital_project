from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from victor_ai_bot import config as config_mod
from victor_ai_bot.config import load_configs_from_env
from victor_ai_bot.deploy_mode import enforce_public_defaults


class _ExplodingExecution:
    @property
    def withdraw_mode(self):
        return "public"

    @withdraw_mode.setter
    def withdraw_mode(self, value):
        raise TypeError("withdraw_mode read-only")

    dry_run = False
    auto_trading = True


class _ExplodingDryRunExecution:
    withdraw_mode = "public"
    auto_trading = True

    @property
    def dry_run(self):
        return False

    @dry_run.setter
    def dry_run(self, value):
        raise ValueError("dry_run locked")


class _CfgNoExecution:
    pass


class _CfgExplodingExecution:
    execution = _ExplodingExecution()


class _CfgExplodingDryRunExecution:
    execution = _ExplodingDryRunExecution()


@pytest.mark.parametrize(
    "cfg",
    [
        _CfgNoExecution(),
        _CfgExplodingExecution(),
        _CfgExplodingDryRunExecution(),
    ],
)
def test_enforce_public_defaults_contained_safe_config_shape_failures(monkeypatch, cfg):
    monkeypatch.setenv("VICTOR_DEPLOYMENT_MODE", "public")
    monkeypatch.delenv("VICTOR_PUBLIC_ALLOW_BROADCAST", raising=False)

    enforce_public_defaults(cfg)


def test_load_configs_from_env_skips_expected_invalid_entries(monkeypatch):
    monkeypatch.setenv("VICTOR_MULTI_CONFIGS", "bad-a.yaml,bad-b.yaml,good.yaml")

    calls = []

    def fake_load_config(path: str):
        calls.append(path)
        if path == "bad-a.yaml":
            raise FileNotFoundError(path)
        if path == "bad-b.yaml":
            raise yaml.YAMLError("bad yaml")
        return SimpleNamespace(name=path)

    monkeypatch.setattr(config_mod, "load_config", fake_load_config)

    cfgs = load_configs_from_env("fallback.yaml")

    assert [c.name for c in cfgs] == ["good.yaml"]
    assert calls == ["bad-a.yaml", "bad-b.yaml", "good.yaml"]


def test_load_configs_from_env_propagates_unexpected_loader_errors(monkeypatch):
    monkeypatch.setenv("VICTOR_MULTI_CONFIGS", "boom.yaml")

    def fake_load_config(path: str):
        raise KeyError("boom")

    monkeypatch.setattr(config_mod, "load_config", fake_load_config)

    with pytest.raises(KeyError, match="boom"):
        load_configs_from_env("fallback.yaml")


def test_load_config_records_source_path(tmp_path: Path):
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(
        "chain:\n  name: local\n  chain_id: 1\n",
        encoding="utf-8",
    )

    cfg = config_mod.load_config(str(cfg_file))

    assert getattr(cfg, "_source_path") == str(cfg_file)
