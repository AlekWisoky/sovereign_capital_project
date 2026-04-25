from types import SimpleNamespace

import pytest

from victor_ai_bot.config_validation import enforce_or_warn, validate_config


class _ExplodingIterable:
    def __iter__(self):
        raise RuntimeError("boom")


def _cfg(
    *,
    rpc_read=None,
    rpc_send=None,
    rpc_private=None,
    dry_run=True,
    send_mode='public',
    base_borrow='0',
    executor='',
    key_env='VICTOR_PRIVATE_KEY',
    slippage=50,
    v3_pairs=None,
):
    chain = SimpleNamespace(
        rpc_read=rpc_read,
        rpc_send=rpc_send,
        rpc_private=rpc_private,
        v3_pairs=v3_pairs if v3_pairs is not None else [],
        curve_pools=[],
        balancer_pools=[],
    )
    execution = SimpleNamespace(
        dry_run=dry_run,
        send_mode=send_mode,
        base_borrow_amount=base_borrow,
        executor_address=executor,
        private_key_env=key_env,
    )
    safety = SimpleNamespace(slippage_bps=slippage)
    return SimpleNamespace(chain=chain, execution=execution, safety=safety)


def test_validate_config_reports_non_listlike_rpc_sources_and_invalid_ints_without_crashing():
    cfg = _cfg(
        rpc_read=_ExplodingIterable(),
        rpc_send=_ExplodingIterable(),
        rpc_private='not-a-list',
        dry_run=False,
        send_mode='private',
        base_borrow='oops',
        slippage='bad',
        v3_pairs=[{'amount_in': object()}],
    )

    ok, issues = validate_config(cfg)

    assert ok is False
    assert 'WARN: chain.rpc_read is not list-like' in issues
    assert 'WARN: chain.rpc_send is not list-like' in issues
    assert 'WARN: chain.rpc_private is not list-like' in issues
    assert 'WARN: execution.base_borrow_amount is not a valid integer string' in issues
    assert 'WARN: safety.slippage_bps is not int' in issues
    assert 'chain.rpc_read is empty (scanner cannot run)' in issues
    assert 'chain.rpc_send is empty but execution.dry_run=false (cannot send txs)' in issues
    assert 'WARN: amount_in resolves to 0 (set execution.base_borrow_amount or any pool amount_in)' in issues


def test_validate_config_accepts_positive_amount_in_from_listlike_pool_config():
    cfg = _cfg(
        rpc_read=['http://read'],
        rpc_send=['http://send'],
        rpc_private=[],
        dry_run=True,
        base_borrow='0',
        v3_pairs=({'amount_in': '25'},),
    )

    ok, issues = validate_config(cfg)

    assert ok is True
    assert 'WARN: amount_in resolves to 0 (set execution.base_borrow_amount or any pool amount_in)' not in issues


def test_enforce_or_warn_raises_in_strict_mode_for_fatals(monkeypatch):
    cfg = _cfg(rpc_read=[], rpc_send=[])
    monkeypatch.setenv('VICTOR_VALIDATE_CONFIG', '1')

    with pytest.raises(ValueError, match='config_validation_failed'):
        enforce_or_warn(cfg)
