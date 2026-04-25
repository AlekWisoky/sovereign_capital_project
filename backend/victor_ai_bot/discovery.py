from __future__ import annotations

import json
import os
from .determinism import stable_hash_int
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


_SAFE_DISCOVERY_ENTRY_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_DISCOVERY_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)
_SAFE_DISCOVERY_SAVE_EXCEPTIONS = (OSError, TypeError, ValueError)
_SAFE_DISCOVERY_RUNTIME_EXCEPTIONS = (AttributeError, TypeError, ValueError, RuntimeError, OSError)

from .ethabi import selector, enc_address, enc_uint
from .rpc import JsonRpcClient


def _hex0x(b: bytes) -> str:
    return "0x" + b.hex()


def _decode_address(ret_hex: str) -> str:
    if not isinstance(ret_hex, str) or not ret_hex.startswith("0x"):
        return ""
    b = bytes.fromhex(ret_hex[2:])
    if len(b) < 32:
        return ""
    # address is rightmost 20 bytes of the 32-byte word
    return "0x" + b[-20:].hex()


@dataclass
class DiscoveredV3:
    token0: str
    token1: str
    fee: int
    pool: str
    first_seen_block: int
    last_seen_block: int

    def to_pair(self) -> Dict[str, Any]:
        # Scanner expects v3_pairs entries of {token_in, token_out, fee}
        return {
            "token_in": self.token0,
            "token_out": self.token1,
            "fee": int(self.fee),
            "pool": self.pool,
        }


class DiscoveryManager:
    """Bounded, persistent discovery of pools without runaway RPC usage.

    Design goals:
    - Optional and disabled by default (cfg.flags.enable_discovery)
    - Runs infrequently (chain.discovery_interval_blocks)
    - Hard cap on RPC calls per run (chain.discovery_max_calls)
    - Persisted to disk under backend/data/discovery/

    Currently implemented:
    - Uniswap V3 Factory getPool(tokenA, tokenB, fee) discovery

    Safety defaults:
    - If factory or token_universe is missing, discovery is a no-op.
    """

    def __init__(self, *, chain_name: str, data_dir: str):
        self.chain_name = chain_name
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "discovery", f"{chain_name}.json")
        self._last_run_block: int = 0
        self._v3: Dict[str, DiscoveredV3] = {}
        self._load()

    def _load(self) -> None:
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as f:
                j = json.load(f)
            if not isinstance(j, dict):
                return
            v3 = j.get("v3")
            if isinstance(v3, list):
                for it in v3:
                    try:
                        dv = DiscoveredV3(
                            token0=str(it.get("token0") or ""),
                            token1=str(it.get("token1") or ""),
                            fee=int(it.get("fee") or 0),
                            pool=str(it.get("pool") or ""),
                            first_seen_block=int(it.get("first_seen_block") or 0),
                            last_seen_block=int(it.get("last_seen_block") or 0),
                        )
                        if dv.token0 and dv.token1 and dv.pool and dv.fee:
                            self._v3[self._key(dv.token0, dv.token1, dv.fee)] = dv
                    except _SAFE_DISCOVERY_ENTRY_EXCEPTIONS:
                        continue
        except _SAFE_DISCOVERY_LOAD_EXCEPTIONS:
            return

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            payload = {
                "v": 1,
                "ts": int(time.time()),
                "v3": [
                    {
                        "token0": v.token0,
                        "token1": v.token1,
                        "fee": int(v.fee),
                        "pool": v.pool,
                        "first_seen_block": int(v.first_seen_block),
                        "last_seen_block": int(v.last_seen_block),
                    }
                    for v in self._v3.values()
                ],
            }
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self.path)
        except _SAFE_DISCOVERY_SAVE_EXCEPTIONS:
            return

    @staticmethod
    def _key(a: str, b: str, fee: int) -> str:
        # normalized by address ordering
        a0 = a.lower()
        b0 = b.lower()
        if a0 <= b0:
            return f"{a0}:{b0}:{int(fee)}"
        return f"{b0}:{a0}:{int(fee)}"

    def v3_pairs(self) -> List[Dict[str, Any]]:
        return [dv.to_pair() for dv in self._v3.values()]

    async def maybe_discover_univ3(
        self, rpc: JsonRpcClient, cfg: Any, block_number: int
    ) -> List[Dict[str, Any]]:
        """Return extra v3_pairs entries discovered so far (may also discover new ones)."""
        try:
            enabled = bool(getattr(cfg.flags, "enable_discovery", False))
            if not enabled:
                return self.v3_pairs()

            factory = str(getattr(cfg.chain, "univ3_factory", "") or "")
            toks = list(getattr(cfg.chain, "token_universe", []) or [])
            interval = int(getattr(cfg.chain, "discovery_interval_blocks", 50) or 50)
            max_calls = int(getattr(cfg.chain, "discovery_max_calls", 24) or 24)

            if not factory or len(toks) < 2 or max_calls <= 0:
                return self.v3_pairs()

            if self._last_run_block and (block_number - self._last_run_block) < interval:
                return self.v3_pairs()

            self._last_run_block = int(block_number)

            # Fee tiers: keep small; configurable via env if needed.
            fee_tiers = [100, 500, 3000, 10000]

            # Deterministic sampling per block to keep load stable (no RNG).
            seed = f"disc:{int(block_number)}:{self.chain_name}"

            # Build candidate token pairs (bounded).
            pairs: List[Tuple[str, str]] = []
            # Prefer pairs with WETH if present (common arb hub).
            weth = str(getattr(cfg.chain, "weth", "") or "").lower()
            if weth and any(t.lower() == weth for t in toks):
                others = [t.lower() for t in toks if t.lower() != weth]
                others = sorted(others, key=lambda x: stable_hash_int(f"{seed}:weth:{x}"))
                for t in others[: min(len(others), 12)]:
                    pairs.append((weth, t))

            # Fill remaining with random pairs.
            toks_l = sorted(
                {t.lower() for t in toks if t}, key=lambda x: stable_hash_int(f"{seed}:tok:{x}")
            )
            n = len(toks_l)
            seen = set(pairs)
            # Generate a bounded set of deterministic pairs without O(n^2) blowups.
            target_pairs = min(250, max_calls * max(2, len(fee_tiers)))
            for k in range(target_pairs):
                if n < 2:
                    break
                i = stable_hash_int(f"{seed}:i:{k}") % n
                j = stable_hash_int(f"{seed}:j:{k}") % n
                if i == j:
                    j = (j + 1) % n
                a = toks_l[min(i, j)]
                b = toks_l[max(i, j)]
                if a == b:
                    continue
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                pairs.append((a, b))

            # Selector for getPool(address,address,uint24)
            sig = "getPool(address,address,uint24)"
            sel = selector(sig)

            calls = 0
            added = 0
            for a, b in pairs:
                if calls >= max_calls:
                    break
                if a == b:
                    continue
                for fee in fee_tiers:
                    if calls >= max_calls:
                        break
                    k = self._key(a, b, fee)
                    if k in self._v3:
                        continue
                    data = _hex0x(sel + enc_address(a) + enc_address(b) + enc_uint(int(fee)))
                    r = await rpc.eth_call(factory, data)
                    calls += 1
                    if not r.ok or not isinstance(r.result, str):
                        continue
                    pool = _decode_address(r.result)
                    if not pool or pool.lower() == "0x" + "00" * 20:
                        continue
                    dv = DiscoveredV3(
                        token0=a,
                        token1=b,
                        fee=int(fee),
                        pool=pool,
                        first_seen_block=int(block_number),
                        last_seen_block=int(block_number),
                    )
                    self._v3[k] = dv
                    added += 1

            if added > 0:
                self._save()

            return self.v3_pairs()
        except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
            return self.v3_pairs()
