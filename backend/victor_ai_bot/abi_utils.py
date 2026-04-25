from __future__ import annotations

"""ABI helpers used by execution gating and receipt parsing.

Design goals:
- No brittle external ABI toolchain requirement.
- Use the project's keccak/selector primitive from ethabi.
- Keep helpers pure and easily unit-testable.

NOTE: For production deployments, consider replacing the "best-effort" custom
error decoding with a full ABI registry. This module is intentionally minimal.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .ethabi import keccak256, selector


_SAFE_REVERT_HEX_EXCEPTIONS = (TypeError, ValueError)


def selector_hex(sig: str) -> str:
    return "0x" + selector(sig).hex()


def topic0(sig: str) -> str:
    return "0x" + keccak256(sig.encode("utf-8")).hex()


def _strip_0x(h: str) -> str:
    return h[2:] if isinstance(h, str) and h.startswith("0x") else h


def _read_word(data: bytes, i: int) -> int:
    off = i * 32
    return int.from_bytes(data[off : off + 32], "big")


def _read_bytes(data: bytes, off: int, n: int) -> bytes:
    return data[off : off + n]


def _decode_string(data: bytes, off: int) -> str:
    # ABI encoding: offset -> length -> bytes
    if off + 32 > len(data):
        return ""
    strlen = int.from_bytes(data[off : off + 32], "big")
    start = off + 32
    end = min(start + strlen, len(data))
    return data[start:end].decode("utf-8", errors="replace")


@dataclass
class RevertDecoded:
    kind: str
    message: str
    selector: str = ""


ERROR_STRING_SELECTOR = bytes.fromhex("08c379a0")  # Error(string)
PANIC_SELECTOR = bytes.fromhex("4e487b71")         # Panic(uint256)


def decode_revert_data(revert_data_hex: str) -> RevertDecoded:
    """Decode EVM revert data.

    Supports:
    - Error(string)
    - Panic(uint256)
    - otherwise: returns Custom(<selector>)
    """
    if not revert_data_hex or not isinstance(revert_data_hex, str):
        return RevertDecoded("Unknown", "")
    h = _strip_0x(revert_data_hex)
    try:
        b = bytes.fromhex(h)
    except _SAFE_REVERT_HEX_EXCEPTIONS:
        return RevertDecoded("Unknown", "")
    if len(b) < 4:
        return RevertDecoded("Unknown", "")
    sel = b[:4]
    payload = b[4:]
    if sel == ERROR_STRING_SELECTOR:
        # payload: offset (32) then string
        if len(payload) < 64:
            return RevertDecoded("Error", "")
        off = _read_word(payload, 0)
        msg = _decode_string(payload, off)
        return RevertDecoded("Error", msg, selector="0x" + sel.hex())
    if sel == PANIC_SELECTOR:
        if len(payload) < 32:
            return RevertDecoded("Panic", "")
        code = int.from_bytes(payload[:32], "big")
        return RevertDecoded("Panic", f"0x{code:x}", selector="0x" + sel.hex())
    return RevertDecoded("Custom", "", selector="0x" + sel.hex())


def extract_revert_data(err: Any) -> Optional[str]:
    """Best-effort extraction of revert payload from JSON-RPC error objects."""
    if not err:
        return None
    # common shapes:
    # {"code":..., "message":..., "data":"0x..."}
    if isinstance(err, dict):
        data = err.get("data")
        if isinstance(data, str) and data.startswith("0x"):
            return data
        # nested: {"data": {"data": "0x..."}}
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, str) and inner.startswith("0x"):
                return inner
        # geth sometimes: {"data": "Reverted 0x..."}
        if isinstance(data, str) and "0x" in data:
            i = data.find("0x")
            return data[i:]
    # string
    if isinstance(err, str) and "0x" in err:
        i = err.find("0x")
        return err[i:]
    return None
