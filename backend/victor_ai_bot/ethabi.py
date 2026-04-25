from __future__ import annotations
import hashlib
from typing import List


def _keccak256_pure(data: bytes) -> bytes:
    """Pure-Python Keccak-256 (Ethereum) implementation.

    We keep a dependency-free fallback for environments where `eth-hash` or
    `pycryptodome` are not installed.
    """

    RC = [
        0x0000000000000001,
        0x0000000000008082,
        0x800000000000808A,
        0x8000000080008000,
        0x000000000000808B,
        0x0000000080000001,
        0x8000000080008081,
        0x8000000000008009,
        0x000000000000008A,
        0x0000000000000088,
        0x0000000080008009,
        0x000000008000000A,
        0x000000008000808B,
        0x800000000000008B,
        0x8000000000008089,
        0x8000000000008003,
        0x8000000000008002,
        0x8000000000000080,
        0x000000000000800A,
        0x800000008000000A,
        0x8000000080008081,
        0x8000000000008080,
        0x0000000080000001,
        0x8000000080008008,
    ]

    r = [
        [0, 36, 3, 41, 18],
        [1, 44, 10, 45, 2],
        [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56],
        [27, 20, 39, 8, 14],
    ]

    def rol(x: int, n: int) -> int:
        n &= 63
        return ((x << n) | (x >> (64 - n))) & ((1 << 64) - 1)

    def keccak_f(s: list[int]) -> None:
        for rnd in range(24):
            C = [s[x] ^ s[x + 5] ^ s[x + 10] ^ s[x + 15] ^ s[x + 20] for x in range(5)]
            D = [C[(x - 1) % 5] ^ rol(C[(x + 1) % 5], 1) for x in range(5)]
            for x in range(5):
                dx = D[x]
                for y in range(5):
                    s[x + 5 * y] ^= dx

            B = [0] * 25
            for x in range(5):
                for y in range(5):
                    B[y + 5 * ((2 * x + 3 * y) % 5)] = rol(s[x + 5 * y], r[x][y])

            for x in range(5):
                for y in range(5):
                    s[x + 5 * y] = B[x + 5 * y] ^ (
                        (~B[((x + 1) % 5) + 5 * y]) & B[((x + 2) % 5) + 5 * y]
                    )

            s[0] ^= RC[rnd]

    rate_bytes = 136  # Keccak-256 rate (1088 bits)
    out_bytes = 32

    # pad10*1 with domain 0x01 for Keccak
    padded = bytearray(data)
    padded.append(0x01)
    while (len(padded) % rate_bytes) != rate_bytes - 1:
        padded.append(0x00)
    padded.append(0x80)

    s = [0] * 25
    for off in range(0, len(padded), rate_bytes):
        block = padded[off : off + rate_bytes]
        for i in range(rate_bytes // 8):
            s[i] ^= int.from_bytes(block[i * 8 : (i + 1) * 8], "little")
        keccak_f(s)

    out = bytearray()
    while len(out) < out_bytes:
        for i in range(rate_bytes // 8):
            out.extend(int(s[i]).to_bytes(8, "little"))
            if len(out) >= out_bytes:
                break
        if len(out) >= out_bytes:
            break
        keccak_f(s)

    return bytes(out[:out_bytes])


def keccak256(data: bytes) -> bytes:
    """Keccak-256 hash (Ethereum)."""

    # Preferred: eth-hash (keccak-256)
    try:
        from eth_hash.auto import keccak  # type: ignore

        return keccak(data)
    except ImportError:
        pass
    # Fallback: pycryptodome
    try:
        from Crypto.Hash import keccak as _keccak  # type: ignore

        k = _keccak.new(digest_bits=256)
        k.update(data)
        return k.digest()
    except ImportError:
        pass
    # Dependency-free fallback.
    return _keccak256_pure(data)


def selector(sig: str) -> bytes:
    return keccak256(sig.encode("utf-8"))[:4]


def zpad32(b: bytes) -> bytes:
    return b.rjust(32, b"\x00")


def enc_uint(n: int) -> bytes:
    if n < 0:
        raise ValueError("uint cannot be negative")
    return n.to_bytes(32, "big")


def enc_int(n: int) -> bytes:
    if n >= 0:
        return n.to_bytes(32, "big")
    return (2**256 + n).to_bytes(32, "big")


def enc_address(addr: str) -> bytes:
    a = addr.lower()
    if a.startswith("0x"):
        a = a[2:]
    raw = bytes.fromhex(a.rjust(40, "0"))
    return zpad32(raw)


def enc_bool(v: bool) -> bytes:
    return enc_uint(1 if v else 0)


def enc_bytes32(b32: bytes) -> bytes:
    if len(b32) != 32:
        raise ValueError("bytes32 must be 32 bytes")
    return b32


def _pad32(b: bytes) -> bytes:
    return b + b"\x00" * ((32 - (len(b) % 32)) % 32)


def enc_bytes_dyn(b: bytes) -> bytes:
    return enc_uint(len(b)) + _pad32(b)


def decode_int256_array(data: bytes) -> List[int]:
    if len(data) < 32:
        return []
    off = int.from_bytes(data[0:32], "big")
    if off + 32 > len(data):
        return []
    ln = int.from_bytes(data[off : off + 32], "big")
    out = []
    p = off + 32
    for _ in range(ln):
        w = int.from_bytes(data[p : p + 32], "big")
        if w >= 2**255:
            w = w - 2**256
        out.append(w)
        p += 32
    return out
