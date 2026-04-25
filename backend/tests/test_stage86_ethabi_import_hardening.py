from __future__ import annotations

import builtins

import pytest

from victor_ai_bot import ethabi


def test_keccak256_falls_back_when_optional_hash_modules_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"eth_hash.auto", "Crypto.Hash"}:
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    out = ethabi.keccak256(b"abc")
    assert isinstance(out, bytes)
    assert len(out) == 32


def test_keccak256_does_not_swallow_unexpected_eth_hash_import_bug(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "eth_hash.auto":
            raise RuntimeError("boom")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="boom"):
        ethabi.keccak256(b"abc")


def test_keccak256_does_not_swallow_unexpected_crypto_import_bug(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "eth_hash.auto":
            raise ImportError(name)
        if name == "Crypto.Hash":
            raise RuntimeError("boom2")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="boom2"):
        ethabi.keccak256(b"abc")
