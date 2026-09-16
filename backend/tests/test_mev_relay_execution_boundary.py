from types import SimpleNamespace

import pytest

from victor_ai_bot import execution
from victor_ai_bot.execution import try_execute_opportunity


class _Rpc:
    async def estimate_gas(self, tx):
        return 21_000

    async def get_nonce(self, addr):
        return 1

    async def send_raw_tx(self, raw):
        return SimpleNamespace(ok=True, result="0xpublic", error="")

    async def send_private_tx(self, raw, max_block_number=None):
        raise AssertionError("private RPC must be reached through RelayClient")


class _Account:
    address = "0x" + "1" * 40

    @classmethod
    def from_key(cls, key):
        return cls()

    @classmethod
    def sign_transaction(cls, tx, key):
        return SimpleNamespace(raw_transaction=b"signed")


class _Opp:
    route = SimpleNamespace(
        legs=[
            SimpleNamespace(
                amount_in="100",
                min_out="120",
                dex="univ3",
                venue="0x" + "2" * 40,
                token_in="0x" + "3" * 40,
                token_out="0x" + "4" * 40,
                data="0x",
            )
        ]
    )
    min_outs = ["120"]
    meta = {}
    route_id = "route-1"


def _cfg():
    return SimpleNamespace(
        execution=SimpleNamespace(
            dry_run=False,
            max_submit_per_block=1,
            send_mode="private",
            gas_mode="fast",
            gas_presets={},
            gas_limit=21_000,
            private_key_env="EXEC_KEY",
            from_address="0x" + "1" * 40,
            executor_address="0x" + "5" * 40,
            profit_to="0x" + "1" * 40,
            deadline_seconds=30,
            flashloan_fee_bps=9,
            flash_provider="aave",
        ),
        safety=SimpleNamespace(
            minProfitAbs=1,
            minProfitBps=1,
            slippage_bps=50,
            max_borrow_amount="0",
            require_estimate_gas=False,
            require_simulation=False,
            mev_adversarial_eval_enabled=False,
        ),
        chain=SimpleNamespace(chain_id=1),
    )


@pytest.mark.asyncio
async def test_private_execution_routes_through_relay_client(monkeypatch):
    class _Relay:
        calls = []

        def __init__(self, rpc, *, quality_store=None):
            self.rpc = rpc
            self.quality_store = quality_store

        async def send_private_transaction(self, raw_tx_hex, *, max_block=None):
            self.calls.append({
                "raw": raw_tx_hex,
                "max_block": max_block,
                "quality_store": self.quality_store,
            })
            return SimpleNamespace(ok=True, result="0xprivate", error="")

    monkeypatch.setattr(execution, "RelayClient", _Relay)
    monkeypatch.setattr(execution, "Account", _Account)
    monkeypatch.setattr(execution, "build_execute_calldata", lambda **kwargs: ("0x1234", "route-1"))
    monkeypatch.setattr(
        execution,
        "check_profit_and_repay",
        lambda **kwargs: SimpleNamespace(
            ok=True,
            flashloan_fee_wei=1,
            gas_cost_wei=1,
            profit_after_costs_wei=10,
            reason="ok",
        ),
    )

    async def _gas(*args, **kwargs):
        return 1, 1

    monkeypatch.setattr(execution, "suggest_gas", _gas)
    monkeypatch.setenv("EXEC_KEY", "0x" + "11" * 32)
    quality_store = object()

    result = await try_execute_opportunity(
        _Rpc(),
        _Rpc(),
        _cfg(),
        _Opp(),
        current_block=100,
        last_submitted_block=99,
        endpoint_quality=quality_store,
    )

    assert result.ok is True
    assert result.tx_hash == "0xprivate"
    assert _Relay.calls == [
        {"raw": "0x7369676e6564", "max_block": 102, "quality_store": quality_store}
    ]
