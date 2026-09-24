from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .determinism import stable_hash_int
from .ethabi import enc_address, enc_uint, selector
from .rpc import JsonRpcClient

_SAFE_DISCOVERY_ENTRY_EXCEPTIONS = (AttributeError, TypeError, ValueError, IndexError)
_SAFE_DISCOVERY_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)
_SAFE_DISCOVERY_SAVE_EXCEPTIONS = (OSError, TypeError, ValueError)
_SAFE_DISCOVERY_RUNTIME_EXCEPTIONS = (
    AttributeError, TypeError, ValueError, RuntimeError, OSError, IndexError
)
_ZERO_ADDRESS = "0x" + "00" * 20


def _hex0x(b: bytes) -> str:
    return "0x" + b.hex()


def _decode_address(ret_hex: str) -> str:
    if not isinstance(ret_hex, str) or not ret_hex.startswith("0x"):
        return ""
    try:
        b = bytes.fromhex(ret_hex[2:])
    except ValueError:
        return ""
    if len(b) < 32:
        return ""
    return "0x" + b[-20:].hex()


def _words(ret_hex: Any) -> List[bytes]:
    if not isinstance(ret_hex, str) or not ret_hex.startswith("0x"):
        return []
    try:
        raw = bytes.fromhex(ret_hex[2:])
    except ValueError:
        return []
    return [raw[i:i + 32] for i in range(0, len(raw) - 31, 32)]


def _decode_fixed_addresses(ret_hex: Any, size: int = 8) -> List[str]:
    out: List[str] = []
    for word in _words(ret_hex)[:size]:
        addr = "0x" + word[-20:].hex()
        out.append(addr)
    return out


def _decode_fixed_uints(ret_hex: Any, size: int = 8) -> List[int]:
    return [int.from_bytes(w, "big") for w in _words(ret_hex)[:size]]


def _decode_dynamic_array(ret_hex: Any, index: int) -> List[bytes]:
    words = _words(ret_hex)
    if index >= len(words):
        return []
    offset = int.from_bytes(words[index], "big")
    if offset < 0 or offset % 32 or offset // 32 >= len(words):
        return []
    start = offset // 32
    if start >= len(words):
        return []
    length = int.from_bytes(words[start], "big")
    return words[start + 1:start + 1 + length]


def _decode_balancer_pool_tokens(ret_hex: Any) -> Tuple[List[str], List[int]]:
    token_words = _decode_dynamic_array(ret_hex, 0)
    balance_words = _decode_dynamic_array(ret_hex, 1)
    tokens = ["0x" + w[-20:].hex() for w in token_words]
    balances = [int.from_bytes(w, "big") for w in balance_words]
    return tokens, balances


@dataclass
class DiscoveredV3:
    token0: str
    token1: str
    fee: int
    pool: str
    first_seen_block: int
    last_seen_block: int

    def to_pair(self) -> Dict[str, Any]:
        return {
            "token_in": self.token0,
            "token_out": self.token1,
            "fee": int(self.fee),
            "pool": self.pool,
        }


@dataclass
class DiscoveredCurve:
    pool: str
    token_in: str
    token_out: str
    i: int
    j: int
    first_seen_block: int
    last_seen_block: int

    def to_pool(self) -> Dict[str, Any]:
        return {
            "pool": self.pool,
            "token_in": self.token_in,
            "token_out": self.token_out,
            "i": int(self.i),
            "j": int(self.j),
            "underlying": False,
        }


@dataclass
class DiscoveredBalancer:
    pool_id: str
    token_in: str
    token_out: str
    pool: str
    first_seen_block: int
    last_seen_block: int

    def to_pool(self) -> Dict[str, Any]:
        return {
            "pool_id": self.pool_id,
            "pool": self.pool,
            "token_in": self.token_in,
            "token_out": self.token_out,
        }


class DiscoveryManager:
    """Bounded, persistent read-only discovery for route construction.

    UniV3 uses the configured factory. Curve uses its canonical AddressProvider
    to resolve the current registry, then samples a bounded tail of pool ids.
    Balancer uses the canonical Vault's PoolRegistered logs and verifies each
    candidate through getPoolTokens(). No pool address is hard-coded.

    Discovery is observational only. Quote/economic/admission logic remains in
    the existing arb_engine -> execution_capture path.
    """

    def __init__(self, *, chain_name: str, data_dir: str):
        self.chain_name = chain_name
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "discovery", f"{chain_name}.json")
        self._last_run_block: int = 0
        self._last_venue_run_block: int = 0
        self._v3: Dict[str, DiscoveredV3] = {}
        self._curve: Dict[str, DiscoveredCurve] = {}
        self._balancer: Dict[str, DiscoveredBalancer] = {}
        self._load()

    def _load(self) -> None:
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as f:
                j = json.load(f)
            if not isinstance(j, dict):
                return
            for it in j.get("v3") or []:
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
            for it in j.get("curve") or []:
                try:
                    dc = DiscoveredCurve(
                        pool=str(it.get("pool") or ""),
                        token_in=str(it.get("token_in") or ""),
                        token_out=str(it.get("token_out") or ""),
                        i=int(it.get("i") or 0),
                        j=int(it.get("j") or 0),
                        first_seen_block=int(it.get("first_seen_block") or 0),
                        last_seen_block=int(it.get("last_seen_block") or 0),
                    )
                    if dc.pool and dc.token_in and dc.token_out and dc.i != dc.j:
                        self._curve[self._curve_key(dc.pool, dc.i, dc.j)] = dc
                except _SAFE_DISCOVERY_ENTRY_EXCEPTIONS:
                    continue
            for it in j.get("balancer") or []:
                try:
                    db = DiscoveredBalancer(
                        pool_id=str(it.get("pool_id") or ""),
                        pool=str(it.get("pool") or ""),
                        token_in=str(it.get("token_in") or ""),
                        token_out=str(it.get("token_out") or ""),
                        first_seen_block=int(it.get("first_seen_block") or 0),
                        last_seen_block=int(it.get("last_seen_block") or 0),
                    )
                    if db.pool_id and db.pool and db.token_in and db.token_out:
                        self._balancer[self._balancer_key(db.pool_id, db.token_in, db.token_out)] = db
                except _SAFE_DISCOVERY_ENTRY_EXCEPTIONS:
                    continue
        except _SAFE_DISCOVERY_LOAD_EXCEPTIONS:
            return

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            payload = {
                "v": 2,
                "ts": int(time.time()),
                "v3": [vars(v) for v in self._v3.values()],
                "curve": [vars(v) for v in self._curve.values()],
                "balancer": [vars(v) for v in self._balancer.values()],
            }
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self.path)
        except _SAFE_DISCOVERY_SAVE_EXCEPTIONS:
            return

    @staticmethod
    def _key(a: str, b: str, fee: int) -> str:
        a0, b0 = a.lower(), b.lower()
        return f"{a0}:{b0}:{int(fee)}" if a0 <= b0 else f"{b0}:{a0}:{int(fee)}"

    @staticmethod
    def _curve_key(pool: str, i: int, j: int) -> str:
        return f"{pool.lower()}:{int(i)}:{int(j)}"

    @staticmethod
    def _balancer_key(pool_id: str, token_in: str, token_out: str) -> str:
        return f"{pool_id.lower()}:{token_in.lower()}:{token_out.lower()}"

    def v3_pairs(self) -> List[Dict[str, Any]]:
        return [dv.to_pair() for dv in self._v3.values()]

    def curve_pools(self) -> List[Dict[str, Any]]:
        return sorted(
            (dc.to_pool() for dc in self._curve.values()),
            key=lambda p: (str(p.get("pool") or "").lower(), str(p.get("token_in") or "").lower(), str(p.get("token_out") or "").lower(), int(p.get("i") or 0), int(p.get("j") or 0)),
        )

    def balancer_pools(self) -> List[Dict[str, Any]]:
        return [db.to_pool() for db in self._balancer.values()]

    def _venue_discovery_enabled(self, cfg: Any) -> bool:
        return bool(getattr(cfg.chain, "enable_venue_discovery", False))

    def _supported(self, cfg: Any, tokens: List[str]) -> List[Tuple[int, str]]:
        allowed = {str(t).lower() for t in (getattr(cfg.chain, "token_universe", []) or []) if t}
        return [(i, t) for i, t in enumerate(tokens) if t and t.lower() in allowed]

    async def maybe_discover_univ3(
        self, rpc: JsonRpcClient, cfg: Any, block_number: int
    ) -> List[Dict[str, Any]]:
        try:
            if not bool(getattr(cfg.flags, "enable_discovery", False)):
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
            fee_tiers = [100, 500, 3000, 10000]
            seed = f"disc:{int(block_number)}:{self.chain_name}"
            pairs: List[Tuple[str, str]] = []
            weth = str(getattr(cfg.chain, "weth", "") or "").lower()
            if weth and any(t.lower() == weth for t in toks):
                others = [t.lower() for t in toks if t.lower() != weth]
                others = sorted(others, key=lambda x: stable_hash_int(f"{seed}:weth:{x}"))
                pairs.extend((weth, t) for t in others[:12])
            toks_l = sorted({t.lower() for t in toks if t}, key=lambda x: stable_hash_int(f"{seed}:tok:{x}"))
            n = len(toks_l)
            seen = set(pairs)
            target_pairs = min(250, max_calls * max(2, len(fee_tiers)))
            for k in range(target_pairs):
                if n < 2:
                    break
                i = stable_hash_int(f"{seed}:i:{k}") % n
                j = stable_hash_int(f"{seed}:j:{k}") % n
                if i == j:
                    j = (j + 1) % n
                a, b = sorted((toks_l[i], toks_l[j]))
                if a != b and (a, b) not in seen:
                    seen.add((a, b))
                    pairs.append((a, b))
            sel = selector("getPool(address,address,uint24)")
            calls = 0
            added = 0
            for a, b in pairs:
                if calls >= max_calls:
                    break
                for fee in fee_tiers:
                    if calls >= max_calls:
                        break
                    k = self._key(a, b, fee)
                    if k in self._v3:
                        continue
                    r = await rpc.eth_call(factory, _hex0x(sel + enc_address(a) + enc_address(b) + enc_uint(fee)))
                    calls += 1
                    if not r.ok or not isinstance(r.result, str):
                        continue
                    pool = _decode_address(r.result)
                    if not pool or pool.lower() == _ZERO_ADDRESS:
                        continue
                    self._v3[k] = DiscoveredV3(a, b, fee, pool, int(block_number), int(block_number))
                    added += 1
            if added:
                self._save()
            return self.v3_pairs()
        except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
            return self.v3_pairs()

    async def maybe_discover_venues(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> Dict[str, List[Dict[str, Any]]]:
        if not self._venue_discovery_enabled(cfg):
            return {"curve": self.curve_pools(), "balancer": self.balancer_pools()}
        interval = max(1, int(getattr(cfg.chain, "discovery_interval_blocks", 50) or 50))
        if self._last_venue_run_block and (int(block_number) - self._last_venue_run_block) < interval:
            return {"curve": self.curve_pools(), "balancer": self.balancer_pools()}
        self._last_venue_run_block = int(block_number)
        changed = False
        try:
            curve_changed = await self._discover_curve(rpc, cfg, block_number)
            balancer_changed = await self._discover_balancer(rpc, cfg, block_number)
            changed = curve_changed or balancer_changed
        except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
            return {"curve": self.curve_pools(), "balancer": self.balancer_pools()}
        if changed:
            self._save()
        return {"curve": self.curve_pools(), "balancer": self.balancer_pools()}

    async def _discover_curve(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> bool:
        provider = str(getattr(cfg.chain, "curve_address_provider", "") or "")
        if not provider:
            return False
        max_pools = max(1, int(getattr(cfg.chain, "discovery_pool_max_candidates", 24) or 24))
        count_r = await rpc.eth_call(provider, _hex0x(selector("get_registry()")))
        registry = _decode_address(count_r.result) if count_r.ok else ""
        if not registry or registry.lower() == _ZERO_ADDRESS:
            return False
        count_r = await rpc.eth_call(registry, _hex0x(selector("pool_count()")))
        if not count_r.ok or not isinstance(count_r.result, str):
            return False
        try:
            count = int.from_bytes(bytes.fromhex(count_r.result[2:]), "big")
        except (ValueError, AttributeError):
            return False
        start = max(0, count - max_pools)
        indices = list(range(start, count))
        # deterministic order, newest pools first.
        changed = False
        for idx in reversed(indices):
            pool_r = await rpc.eth_call(
                registry,
                _hex0x(selector("pool_list(uint256)") + enc_uint(idx)),
            )
            pool = _decode_address(pool_r.result) if pool_r.ok else ""
            if not pool or pool.lower() == _ZERO_ADDRESS:
                continue
            coins_r = await rpc.eth_call(
                registry,
                _hex0x(selector("get_coins(address)") + enc_address(pool)),
            )
            balances_r = await rpc.eth_call(
                registry,
                _hex0x(selector("get_balances(address)") + enc_address(pool)),
            )
            coins = _decode_fixed_addresses(coins_r.result, 8) if coins_r.ok else []
            balances = _decode_fixed_uints(balances_r.result, 8) if balances_r.ok else []
            if not coins or not balances:
                continue
            supported = [
                (i, token)
                for i, token in self._supported(cfg, coins)
                if i < len(balances) and int(balances[i]) > 0
            ]
            if len(supported) < 2:
                continue
            for pos_a, (i, token_a) in enumerate(supported):
                for j, token_b in supported[pos_a + 1:]:
                    if self._curve_key(pool, i, j) not in self._curve:
                        self._curve[self._curve_key(pool, i, j)] = DiscoveredCurve(pool, token_a, token_b, i, j, int(block_number), int(block_number))
                        changed = True
                    if self._curve_key(pool, j, i) not in self._curve:
                        self._curve[self._curve_key(pool, j, i)] = DiscoveredCurve(pool, token_b, token_a, j, i, int(block_number), int(block_number))
                        changed = True
        return changed

    async def _discover_balancer(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> bool:
        vault = str(getattr(cfg.chain, "balancer_vault", "") or "")
        if not vault:
            return False
        latest = int(block_number)
        window = max(1, int(getattr(cfg.chain, "discovery_log_window_blocks", 50000) or 50000))
        from_block = max(0, latest - window)
        topic = "0x3c13bc30b8e878c53fd2a36b679409c073afd75950be43d8858768e956fbc20e"
        logs = await rpc.eth_get_logs(address=vault, from_block=from_block, to_block=latest, topics=[topic])
        max_pools = max(1, int(getattr(cfg.chain, "discovery_pool_max_candidates", 24) or 24))
        for log in logs[-max_pools:]:
            topics = log.get("topics") if isinstance(log, dict) else None
            if not isinstance(topics, list) or len(topics) < 3:
                continue
            pool_id = str(topics[1] or "")
            pool = _decode_address(str(topics[2] or ""))
            if not pool_id or not pool or pool.lower() == _ZERO_ADDRESS:
                continue
            data = log.get("data") if isinstance(log, dict) else None
            if data is None:
                data = "0x"
            # Verify live pool state directly; no pool address is trusted from logs alone.
            r = await rpc.eth_call(
                vault,
                _hex0x(selector("getPoolTokens(bytes32)") + bytes.fromhex(pool_id[2:])),
            )
            if not r.ok:
                continue
            tokens, balances = _decode_balancer_pool_tokens(r.result)
            supported = [
                (i, token)
                for i, token in self._supported(cfg, tokens)
                if i < len(balances) and int(balances[i]) > 0
            ]
            if len(supported) < 2:
                continue
            for pos_a, (_i, token_a) in enumerate(supported):
                for _j, token_b in supported[pos_a + 1:]:
                    if self._balancer_key(pool_id, token_a, token_b) not in self._balancer:
                        self._balancer[self._balancer_key(pool_id, token_a, token_b)] = DiscoveredBalancer(pool_id, token_a, token_b, pool, int(block_number), int(block_number))
                        changed = True
                    if self._balancer_key(pool_id, token_b, token_a) not in self._balancer:
                        self._balancer[self._balancer_key(pool_id, token_b, token_a)] = DiscoveredBalancer(pool_id, token_b, token_a, pool, int(block_number), int(block_number))
                        changed = True
        return changed
