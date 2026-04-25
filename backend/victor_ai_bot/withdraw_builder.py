from __future__ import annotations

"""Executor withdrawal calldata helpers.

The on-chain executor exposes:
- setWithdrawalAllowed(address,bool)
- withdraw(address token,address to,uint256 amount)

We build calldata without heavy ABI dependencies, using victor_ai_bot.ethabi helpers.
"""

from .ethabi import selector, enc_address, enc_uint


def build_set_withdrawal_allowed_calldata(to: str, allowed: bool) -> str:
    sig = "setWithdrawalAllowed(address,bool)"
    sel = selector(sig)
    data = sel + enc_address(to) + enc_uint(1 if allowed else 0)
    return "0x" + data.hex()


def build_withdraw_calldata(token: str, to: str, amount: int) -> str:
    sig = "withdraw(address,address,uint256)"
    sel = selector(sig)
    data = sel + enc_address(token) + enc_address(to) + enc_uint(int(amount))
    return "0x" + data.hex()


def build_convert_and_withdraw_calldata(
    token_in: str,
    token_out: str,
    amount_in: int,
    min_out: int,
    to: str,
    fee: int,
    deadline: int,
) -> str:
    """Build calldata for convertAndWithdraw.

    Solidity signature:
      convertAndWithdraw(address tokenIn,address tokenOut,uint256 amountIn,uint256 minOut,address to,uint24 fee,uint256 deadline)

    Note: uint24 is ABI-encoded as uint256.
    """

    sig = "convertAndWithdraw(address,address,uint256,uint256,address,uint24,uint256)"
    sel = selector(sig)
    data = (
        sel
        + enc_address(token_in)
        + enc_address(token_out)
        + enc_uint(int(amount_in))
        + enc_uint(int(min_out))
        + enc_address(to)
        + enc_uint(int(fee))
        + enc_uint(int(deadline))
    )
    return "0x" + data.hex()
