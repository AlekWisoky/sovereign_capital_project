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
_UNIV3_POOL_CREATED_TOPIC = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
_AERODROME_POOL_CREATED_TOPIC = "0x" + __import__("victor_ai_bot.ethabi", fromlist=["keccak256"]).keccak256(b"PoolCreated(address,address,bool,address,uint256)").hex()
_SLIPSTREAM_POOL_CREATED_TOPIC = "0x" + __import__("victor_ai_bot.ethabi", fromlist=["keccak256"]).keccak256(b"PoolCreated(address,address,int24,address)").hex()


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
class DiscoveredAerodrome:
    pool: str
    token_in: str
    token_out: str
    stable: bool
    factory: str
    first_seen_block: int
    last_seen_block: int

    def to_pool(self) -> Dict[str, Any]:
        return {
            "pool": self.pool,
            "token_in": self.token_in,
            "token_out": self.token_out,
            "stable": bool(self.stable),
            "factory": self.factory,
        }


@dataclass
class DiscoveredSlipstream:
    pool: str
    token_in: str
    token_out: str
    tick_spacing: int
    factory: str
    first_seen_block: int
    last_seen_block: int

    def to_pool(self) -> Dict[str, Any]:
        return {
            "pool": self.pool,
            "token_in": self.token_in,
            "token_out": self.token_out,
            "tick_spacing": int(self.tick_spacing),
            "factory": self.factory,
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
        self._last_aerodrome_run_block: int = 0
        self._last_slipstream_run_block: int = 0
        self._v3: Dict[str, DiscoveredV3] = {}
        self._curve: Dict[str, DiscoveredCurve] = {}
        self._balancer: Dict[str, DiscoveredBalancer] = {}
        self._aerodrome: Dict[str, DiscoveredAerodrome] = {}
        self._slipstream: Dict[str, DiscoveredSlipstream] = {}
        self._candidate_tokens_observed: Dict[str, set[str]] = {}
        self._candidate_token_observation_cap = max(
            1, int(os.environ.get("VICTOR_CANDIDATE_TOKEN_OBSERVATION_CAP", "64") or 64)
        )
        self._candidate_token_observation_truncated = False
        self._load()

    def _observe_candidate_tokens(self, tokens: List[str], *, source: str) -> None:
        for token in tokens:
            normalized = str(token or "").lower()
            if not normalized or normalized == _ZERO_ADDRESS.lower():
                continue
            if normalized not in self._candidate_tokens_observed:
                if len(self._candidate_tokens_observed) >= self._candidate_token_observation_cap:
                    self._candidate_token_observation_truncated = True
                    break
                self._candidate_tokens_observed[normalized] = set()
            self._candidate_tokens_observed[normalized].add(str(source))

    def candidate_token_telemetry(self, cfg: Any) -> Dict[str, Any]:
        execution_universe = sorted({
            str(token).lower()
            for token in (getattr(cfg.chain, "token_universe", []) or [])
            if token
        })
        observed = sorted(self._candidate_tokens_observed.keys())
        not_admitted = [token for token in observed if token not in set(execution_universe)]
        return {
            "execution_universe": execution_universe,
            "observed_tokens": observed,
            "observed_not_admitted": not_admitted,
            "observed_count": len(observed),
            "observed_not_admitted_count": len(not_admitted),
            "observation_cap": int(self._candidate_token_observation_cap),
            "observation_truncated": bool(self._candidate_token_observation_truncated),
            "admission_mutated": False,
            "sources": {
                token: sorted(self._candidate_tokens_observed[token])
                for token in not_admitted[:64]
            },
        }

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
                        self._observe_candidate_tokens(
                            [dv.token0, dv.token1], source="univ3_persisted"
                        )
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
                        self._observe_candidate_tokens(
                            [dc.token_in, dc.token_out], source="curve_persisted"
                        )
                except _SAFE_DISCOVERY_ENTRY_EXCEPTIONS:
                    continue
            for it in j.get("aerodrome") or []:
                try:
                    da = DiscoveredAerodrome(pool=str(it.get("pool") or ""), token_in=str(it.get("token_in") or ""), token_out=str(it.get("token_out") or ""), stable=bool(it.get("stable", False)), factory=str(it.get("factory") or ""), first_seen_block=int(it.get("first_seen_block") or 0), last_seen_block=int(it.get("last_seen_block") or 0))
                    if da.pool and da.token_in and da.token_out and da.factory:
                        self._aerodrome[self._aerodrome_key(da.pool, da.token_in, da.token_out, da.stable, da.factory)] = da
                        self._observe_candidate_tokens([da.token_in, da.token_out], source="aerodrome_persisted")
                except _SAFE_DISCOVERY_ENTRY_EXCEPTIONS:
                    continue
            for it in j.get("slipstream") or []:
                try:
                    ds = DiscoveredSlipstream(pool=str(it.get("pool") or ""), token_in=str(it.get("token_in") or ""), token_out=str(it.get("token_out") or ""), tick_spacing=int(it.get("tick_spacing") or 0), factory=str(it.get("factory") or ""), first_seen_block=int(it.get("first_seen_block") or 0), last_seen_block=int(it.get("last_seen_block") or 0))
                    if ds.pool and ds.token_in and ds.token_out and ds.tick_spacing > 0 and ds.factory:
                        self._slipstream[self._slipstream_key(ds.pool, ds.token_in, ds.token_out, ds.tick_spacing, ds.factory)] = ds
                        self._observe_candidate_tokens([ds.token_in, ds.token_out], source="slipstream_persisted")
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
                        self._observe_candidate_tokens(
                            [db.token_in, db.token_out], source="balancer_persisted"
                        )
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
                "aerodrome": [vars(v) for v in self._aerodrome.values()],
                "slipstream": [vars(v) for v in self._slipstream.values()],
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

    @staticmethod
    def _aerodrome_key(pool: str, token_in: str, token_out: str, stable: bool, factory: str) -> str:
        return f"{pool.lower()}:{token_in.lower()}:{token_out.lower()}:{int(bool(stable))}:{factory.lower()}"

    def v3_pairs(self) -> List[Dict[str, Any]]:
        return [dv.to_pair() for dv in self._v3.values()]

    def curve_pools(self) -> List[Dict[str, Any]]:
        return [dc.to_pool() for dc in self._curve.values()]

    def balancer_pools(self) -> List[Dict[str, Any]]:
        return [db.to_pool() for db in self._balancer.values()]

    def aerodrome_pools(self) -> List[Dict[str, Any]]:
        return [da.to_pool() for da in self._aerodrome.values()]

    @staticmethod
    def _slipstream_key(pool: str, token_in: str, token_out: str, tick_spacing: int, factory: str) -> str:
        return f"{pool.lower()}:{token_in.lower()}:{token_out.lower()}:{int(tick_spacing)}:{factory.lower()}"

    def slipstream_pools(self) -> List[Dict[str, Any]]:
        return [ds.to_pool() for ds in self._slipstream.values()]

    def _venue_discovery_enabled(self, cfg: Any) -> bool:
        return bool(getattr(cfg.chain, "enable_venue_discovery", False))

    def _supported(self, cfg: Any, tokens: List[str]) -> List[Tuple[int, str]]:
        allowed = {str(t).lower() for t in (getattr(cfg.chain, "token_universe", []) or []) if t}
        return [(i, t) for i, t in enumerate(tokens) if t and t.lower() in allowed]

    def _research_frontier_tokens(self, cfg: Any) -> set[str]:
        """Bounded research tokens observed from verified pools; never execution authority."""
        anchors = {str(token).lower() for token in (getattr(cfg.chain, "token_universe", []) or []) if token}
        cap = max(1, min(8, int(os.environ.get("VICTOR_DISCOVERY_FRONTIER_TOKEN_CAP", "8") or 8)))
        observed = sorted(token for token in self._candidate_tokens_observed if token not in anchors)
        return anchors | set(observed[:cap])
    def _supported_discovery_pairs(
        self,
        cfg: Any,
        tokens: List[str],
        balances: List[int],
    ) -> List[Tuple[int, str, int, str]]:
        """Return bounded liquid pairs touching the configured execution universe.

        Discovery may observe a token outside the execution universe, but it must
        never mutate that universe. Once a verified pool contains an execution
        anchor plus another liquid token, however, the pair is valid read-only
        market-discovery evidence and must reach the quote graph; otherwise
        cross-venue/triangle discovery is permanently blind to newly discovered
        edges.
        """
        anchors = self._research_frontier_tokens(cfg)
        liquid: List[Tuple[int, str]] = []
        for index, token in enumerate(tokens):
            normalized = str(token or "").lower()
            if (
                not normalized
                or normalized == _ZERO_ADDRESS.lower()
                or index >= len(balances)
                or int(balances[index] or 0) <= 0
            ):
                continue
            liquid.append((index, str(token)))
        anchor_positions = [item for item in liquid if item[1].lower() in anchors]
        if len(anchor_positions) < 1:
            return []

        pairs: List[Tuple[int, str, int, str]] = []
        seen: set[tuple[int, int]] = set()
        # Anchor-to-anchor and anchor-to-discovered-token edges are both useful.
        # Unknown-to-unknown edges are intentionally excluded to keep discovery
        # bounded and anchored to the configured execution universe.
        for i, token_i in anchor_positions:
            for j, token_j in liquid:
                if i == j:
                    continue
                key = (min(i, j), max(i, j))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append((i, token_i, j, token_j))
        return pairs

    async def maybe_discover_aerodrome(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> List[Dict[str, Any]]:
        try:
            router = str(getattr(cfg.chain, "aerodrome_router", "") or "")
            if not router or not bool(getattr(cfg.flags, "enable_discovery", False)):
                return self.aerodrome_pools()
            interval = int(getattr(cfg.chain, "discovery_interval_blocks", 50) or 50)
            if self._last_aerodrome_run_block and (int(block_number) - self._last_aerodrome_run_block) < interval:
                return self.aerodrome_pools()
            self._last_aerodrome_run_block = int(block_number)
            registry_call = await rpc.eth_call(router, "0x" + selector("factoryRegistry()").hex())
            registry = _decode_address(registry_call.result) if registry_call.ok else ""
            if not registry:
                registry = str(getattr(cfg.chain, "aerodrome_factory_registry", "") or "")
            if not registry:
                return self.aerodrome_pools()
            factories_call = await rpc.eth_call(registry, "0x" + selector("poolFactories()").hex())
            factory_words = _decode_dynamic_array(factories_call.result, 0) if factories_call.ok else []
            factories = ["0x" + word[-20:].hex() for word in factory_words[:16]]
            anchors = self._research_frontier_tokens(cfg)
            window = max(1, int(getattr(cfg.chain, "discovery_log_window_blocks", 50_000) or 50_000))
            max_pools = max(1, int(getattr(cfg.chain, "discovery_pool_max_candidates", 48) or 48))
            changed = False
            for factory in factories[:16]:
                try:
                    logs = await rpc.eth_get_logs(address=factory, from_block=max(0, int(block_number)-window), to_block=int(block_number), topics=[_AERODROME_POOL_CREATED_TOPIC])
                except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
                    continue
                for log in list(logs or [])[-max_pools:]:
                    topics = log.get("topics") if isinstance(log, dict) else None
                    if not isinstance(topics, list) or len(topics) < 4:
                        continue
                    token0, token1 = _decode_address(str(topics[1] or "")), _decode_address(str(topics[2] or ""))
                    stable = bool(int(str(topics[3] or "0"), 16))
                    words = _words(log.get("data") if isinstance(log, dict) else "")
                    pool = "0x" + words[0][-20:].hex() if words else ""
                    if not token0 or not token1 or not pool or not ({token0.lower(), token1.lower()} & anchors):
                        continue
                    self._observe_candidate_tokens([token0, token1], source="aerodrome_pool_created")
                    key = self._aerodrome_key(pool, token0, token1, stable, factory)
                    if key in self._aerodrome:
                        continue
                    self._aerodrome[key] = DiscoveredAerodrome(pool, token0, token1, stable, factory, int(block_number), int(block_number))
                    changed = True
            if changed:
                self._save()
            return self.aerodrome_pools()
        except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
            return self.aerodrome_pools()

    async def maybe_discover_slipstream(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> List[Dict[str, Any]]:
        try:
            factories = [str(x) for x in (getattr(cfg.chain, "slipstream_factories", []) or []) if x]
            if not factories or not bool(getattr(cfg.flags, "enable_discovery", False)):
                return self.slipstream_pools()
            interval = int(getattr(cfg.chain, "discovery_interval_blocks", 50) or 50)
            if self._last_slipstream_run_block and (int(block_number) - self._last_slipstream_run_block) < interval:
                return self.slipstream_pools()
            self._last_slipstream_run_block = int(block_number)
            anchors = self._research_frontier_tokens(cfg)
            window = max(1, int(getattr(cfg.chain, "discovery_log_window_blocks", 50_000) or 50_000))
            max_pools = max(1, int(getattr(cfg.chain, "discovery_pool_max_candidates", 48) or 48))
            changed = False
            for factory in factories[:8]:
                try:
                    logs = await rpc.eth_get_logs(
                        address=factory,
                        from_block=max(0, int(block_number) - window),
                        to_block=int(block_number),
                        topics=[_SLIPSTREAM_POOL_CREATED_TOPIC],
                    )
                except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
                    continue
                for log in list(logs or [])[-max_pools:]:
                    topics = log.get("topics") if isinstance(log, dict) else None
                    if not isinstance(topics, list) or len(topics) < 4:
                        continue
                    token0 = _decode_address(str(topics[1] or ""))
                    token1 = _decode_address(str(topics[2] or ""))
                    try:
                        raw_spacing = int(str(topics[3] or "0"), 16)
                        tick_spacing = raw_spacing - (1 << 256) if raw_spacing >= (1 << 255) else raw_spacing
                    except (TypeError, ValueError):
                        continue
                    words = _words(log.get("data") if isinstance(log, dict) else "")
                    pool = "0x" + words[0][-20:].hex() if words else ""
                    if not token0 or not token1 or not pool or tick_spacing <= 0 or not ({token0.lower(), token1.lower()} & anchors):
                        continue
                    is_pool_data = "0x" + selector("isPool(address)").hex() + enc_address(pool).hex()
                    membership = await rpc.eth_call(factory, is_pool_data)
                    if not membership.ok or not isinstance(membership.result, str) or int(membership.result, 16) == 0:
                        continue
                    liquidity = await rpc.eth_call(pool, "0x" + selector("liquidity()").hex())
                    if not liquidity.ok or not isinstance(liquidity.result, str) or int(liquidity.result, 16) <= 0:
                        continue
                    self._observe_candidate_tokens([token0, token1], source="slipstream_pool_created")
                    key = self._slipstream_key(pool, token0, token1, tick_spacing, factory)
                    if key in self._slipstream:
                        continue
                    self._slipstream[key] = DiscoveredSlipstream(pool, token0, token1, tick_spacing, factory, int(block_number), int(block_number))
                    changed = True
            if changed:
                self._save()
            return self.slipstream_pools()
        except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
            return self.slipstream_pools()

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

            # Consume canonical factory PoolCreated events first. This bounded
            # bridge expands the quote graph only when a discovered pool touches
            # a configured anchor token; economics/execution remain downstream.
            await self._discover_univ3_pool_events(rpc, cfg, int(block_number))
            fee_tiers = [100, 500, 3000, 10000]
            seed = f"disc:{int(block_number)}:{self.chain_name}"
            pairs: List[Tuple[str, str]] = []

            # Discovery is allowed to widen the quote graph without widening the
            # execution token universe.  PoolCreated/Curve/Balancer observations
            # can reveal a liquid token that is absent from the three-token anchor
            # set; use a small deterministic anchor->observed frontier so the next
            # factory queries can find additional UniV3 liquidity for that token.
            # This is intentionally bounded by the existing discovery call cap.
            anchors = sorted(
                {str(token).lower() for token in toks if token},
                key=lambda x: stable_hash_int(f"{seed}:anchor:{x}"),
            )
            observed = sorted(
                {
                    str(token).lower()
                    for token in self._candidate_tokens_observed
                    if str(token).lower() not in set(anchors)
                },
                key=lambda x: stable_hash_int(f"{seed}:frontier:{x}"),
            )
            try:
                frontier_cap = max(
                    1,
                    min(
                        8,
                        int(os.environ.get("VICTOR_DISCOVERY_FRONTIER_TOKEN_CAP", "8") or 8),
                    ),
                )
            except (TypeError, ValueError):
                frontier_cap = 8
            for token in observed[:frontier_cap]:
                for anchor in anchors:
                    if token != anchor:
                        pairs.append((anchor, token))

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

    async def _discover_univ3_pool_events(
        self, rpc: JsonRpcClient, cfg: Any, block_number: int
    ) -> bool:
        factory = str(getattr(cfg.chain, "univ3_factory", "") or "")
        if not factory:
            return False
        window = max(1, int(getattr(cfg.chain, "discovery_log_window_blocks", 50000) or 50000))
        max_pools = max(1, int(getattr(cfg.chain, "discovery_pool_max_candidates", 24) or 24))
        from_block = max(0, int(block_number) - window)
        try:
            logs = await rpc.eth_get_logs(
                address=factory,
                from_block=from_block,
                to_block=int(block_number),
                topics=[_UNIV3_POOL_CREATED_TOPIC],
            )
        except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
            return False
        anchors = self._research_frontier_tokens(cfg)
        changed = False
        for log in list(logs or [])[-max_pools:]:
            topics = log.get("topics") if isinstance(log, dict) else None
            if not isinstance(topics, list) or len(topics) < 4:
                continue
            token0 = _decode_address(str(topics[1] or ""))
            token1 = _decode_address(str(topics[2] or ""))
            try:
                fee = int(str(topics[3] or "0"), 16)
            except (TypeError, ValueError):
                continue
            words = _words(log.get("data") if isinstance(log, dict) else "")
            pool = "0x" + words[1][-20:].hex() if len(words) >= 2 else ""
            if (
                not token0 or not token1 or not pool
                or token0.lower() == _ZERO_ADDRESS.lower()
                or token1.lower() == _ZERO_ADDRESS.lower()
                or pool.lower() == _ZERO_ADDRESS.lower()
                or fee <= 0
                or not ({token0.lower(), token1.lower()} & anchors)
            ):
                continue
            self._observe_candidate_tokens([token0, token1], source="univ3_pool_created")
            key = self._key(token0, token1, fee)
            if key in self._v3:
                continue
            self._v3[key] = DiscoveredV3(
                token0, token1, fee, pool, int(block_number), int(block_number)
            )
            changed = True
        if changed:
            self._save()
        return changed

    async def maybe_discover_venues(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> Dict[str, List[Dict[str, Any]]]:
        if not self._venue_discovery_enabled(cfg):
            return {
                "curve": self.curve_pools(),
                "balancer": self.balancer_pools(),
                "aerodrome": self.aerodrome_pools(),
                "slipstream": self.slipstream_pools(),
            }
        changed = False
        try:
            curve_changed = await self._discover_curve(rpc, cfg, block_number)
            balancer_changed = await self._discover_balancer(rpc, cfg, block_number)
            aerodrome_changed = await self._discover_aerodrome(rpc, cfg, block_number)
            slipstream_changed = await self._discover_slipstream(rpc, cfg, block_number)
            changed = curve_changed or balancer_changed or aerodrome_changed or slipstream_changed
        except _SAFE_DISCOVERY_RUNTIME_EXCEPTIONS:
            return {
                "curve": self.curve_pools(),
                "balancer": self.balancer_pools(),
                "aerodrome": self.aerodrome_pools(),
                "slipstream": self.slipstream_pools(),
            }
        if changed:
            self._save()
        return {
            "curve": self.curve_pools(),
            "balancer": self.balancer_pools(),
            "aerodrome": self.aerodrome_pools(),
            "slipstream": self.slipstream_pools(),
        }

    async def _discover_slipstream(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> bool:
        if not str(getattr(cfg.chain, "slipstream_quoter_v2", "") or ""):
            return False
        result = await self.maybe_discover_slipstream(rpc, cfg, block_number)
        before = len(self._slipstream)
        for row in result:
            if not isinstance(row, dict):
                continue
            key = self._slipstream_key(
                str(row.get("pool") or ""),
                str(row.get("token_in") or ""),
                str(row.get("token_out") or ""),
                int(row.get("tick_spacing") or 0),
                str(row.get("factory") or ""),
            )
            if key not in self._slipstream and row.get("pool") and row.get("factory"):
                self._slipstream[key] = DiscoveredSlipstream(
                    str(row["pool"]), str(row["token_in"]), str(row["token_out"]),
                    int(row["tick_spacing"]), str(row["factory"]),
                    int(block_number), int(block_number),
                )
        return len(self._slipstream) > before

    async def _discover_aerodrome(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> bool:
        if not str(getattr(cfg.chain, "aerodrome_router", "") or ""):
            return False
        result = await self.maybe_discover_aerodrome(rpc, cfg, block_number)
        before = len(self._aerodrome)
        for row in result:
            if not isinstance(row, dict):
                continue
            key = self._aerodrome_key(str(row.get("pool") or ""), str(row.get("token_in") or ""), str(row.get("token_out") or ""), bool(row.get("stable", False)), str(row.get("factory") or ""))
            if key not in self._aerodrome and row.get("pool") and row.get("factory"):
                self._aerodrome[key] = DiscoveredAerodrome(str(row["pool"]), str(row["token_in"]), str(row["token_out"]), bool(row.get("stable", False)), str(row["factory"]), int(block_number), int(block_number))
        return len(self._aerodrome) > before

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
            self._observe_candidate_tokens(coins, source="curve_pool_candidate")
            if not coins or not balances:
                continue
            supported_pairs = self._supported_discovery_pairs(cfg, coins, balances)
            if not supported_pairs:
                continue
            for i, token_a, j, token_b in supported_pairs:
                if self._curve_key(pool, i, j) not in self._curve:
                    self._curve[self._curve_key(pool, i, j)] = DiscoveredCurve(
                        pool, token_a, token_b, i, j, int(block_number), int(block_number)
                    )
                    changed = True
                if self._curve_key(pool, j, i) not in self._curve:
                    self._curve[self._curve_key(pool, j, i)] = DiscoveredCurve(
                        pool, token_b, token_a, j, i, int(block_number), int(block_number)
                    )
                    changed = True
        return changed

    async def _discover_balancer(self, rpc: JsonRpcClient, cfg: Any, block_number: int) -> bool:
        changed = False
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
            self._observe_candidate_tokens(tokens, source="balancer_pool_candidate")
            supported_pairs = self._supported_discovery_pairs(cfg, tokens, balances)
            if not supported_pairs:
                continue
            for _i, token_a, _j, token_b in supported_pairs:
                if self._balancer_key(pool_id, token_a, token_b) not in self._balancer:
                    self._balancer[self._balancer_key(pool_id, token_a, token_b)] = DiscoveredBalancer(
                        pool_id, token_a, token_b, pool, int(block_number), int(block_number)
                    )
                    changed = True
                if self._balancer_key(pool_id, token_b, token_a) not in self._balancer:
                    self._balancer[self._balancer_key(pool_id, token_b, token_a)] = DiscoveredBalancer(
                        pool_id, token_b, token_a, pool, int(block_number), int(block_number)
                    )
                    changed = True
        return changed
