from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp
from eth_hash.auto import keccak

from ..rpc import JsonRpcClient


_SAFE_POOL_EVENT_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    aiohttp.ClientError,
    asyncio.TimeoutError,
)


def _topic(signature: str) -> str:
    return "0x" + keccak(signature.encode("utf-8")).hex()


_SYNC_TOPIC = _topic("Sync(uint112,uint112)")
_V2_SWAP_TOPIC = _topic(
    "Swap(address,uint256,uint256,uint256,uint256,address)"
)
_V3_SWAP_TOPIC = _topic(
    "Swap(address,address,int256,int256,uint160,uint128,int24)"
)
_BALANCER_SWAP_TOPIC = _topic(
    "Swap(bytes32,address,address,uint256,uint256)"
)
_EVENT_TOPICS = (
    _SYNC_TOPIC,
    _V2_SWAP_TOPIC,
    _V3_SWAP_TOPIC,
    _BALANCER_SWAP_TOPIC,
)


@dataclass
class PoolEventState:
    address: str
    kind: str = "unknown"
    token0: str = ""
    token1: str = ""
    last_block: int = 0
    last_event_type: str = ""
    last_tx_hash: str = ""
    reserve0: Optional[int] = None
    reserve1: Optional[int] = None
    sqrt_price_x96: Optional[int] = None
    liquidity: Optional[int] = None
    tick: Optional[int] = None
    amount0: Optional[int] = None
    amount1: Optional[int] = None
    updated_at_ms: int = 0


@dataclass
class PoolStateEventCache:
    """Bounded event-fed pool state and affected-edge priority cache.

    This cache is discovery-first and execution-neutral:
    - WebSocket logs are used as the fast change signal.
    - Small HTTP log reconciliation repairs missed WS events.
    - The cache never authorizes execution or replaces final RPC revalidation.
    - Edge ordering changes only discovery priority, never the economic truth gate.
    """

    chain_name: str
    chain_id: int
    ws_urls: List[str] = field(default_factory=list)
    rpc_urls: List[str] = field(default_factory=list)
    max_addresses: int = 256
    reconcile_max_blocks: int = 200
    refresh_interval_s: float = 15.0

    def __post_init__(self) -> None:
        self.ws_urls = [
            str(url).strip() for url in (self.ws_urls or []) if str(url).strip()
        ]
        self.rpc_urls = [
            str(url).strip() for url in (self.rpc_urls or []) if str(url).strip()
        ]
        self.max_addresses = max(16, min(1024, int(self.max_addresses)))
        self.reconcile_max_blocks = max(1, min(2000, int(self.reconcile_max_blocks)))
        self.refresh_interval_s = max(3.0, min(60.0, float(self.refresh_interval_s)))
        self._tracked: Dict[str, Dict[str, Any]] = {}
        self._states: Dict[str, PoolEventState] = {}
        self._dirty: set[str] = set()
        self._last_seen_block = 0
        self._event_count = 0
        self._reconcile_count = 0
        self._reconcile_missed = 0
        self._address_version = 0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._ws_cursor = 0
        self._connected = False
        self._last_error = ""
        self._last_message_ts = 0.0
        self._subscribed_address_count = 0
        self._truncated = False
        self._last_candidate_metrics: Dict[str, Any] = {}

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        self._connected = False

    def refresh_edges(
        self,
        edges: Iterable[Any],
        *,
        balancer_vault: str = "",
    ) -> None:
        tracked: Dict[str, Dict[str, Any]] = {}
        for edge in list(edges or []):
            address = self._edge_pool_address(edge)
            if not address:
                continue
            entry = tracked.setdefault(
                address,
                {"kind": str(getattr(edge, "dex", "unknown") or "unknown"), "tokens": set()},
            )
            entry["tokens"].update(
                {
                    str(getattr(edge, "token_in", "") or "").lower(),
                    str(getattr(edge, "token_out", "") or "").lower(),
                }
            )
        vault = str(balancer_vault or "").strip().lower()
        if vault:
            tracked.setdefault(vault, {"kind": "balancer_vault", "tokens": set()})

        normalized: Dict[str, Dict[str, Any]] = {}
        for address, entry in tracked.items():
            tokens = sorted(token for token in set(entry.get("tokens") or set()) if token)
            normalized[address] = {
                "kind": str(entry.get("kind") or "unknown"),
                "tokens": tokens[:2],
            }

        changed = (
            set(normalized) != set(self._tracked)
            or any(normalized.get(k) != self._tracked.get(k) for k in normalized)
        )
        self._tracked = normalized
        for address, entry in normalized.items():
            tokens = list(entry.get("tokens") or [])
            state = self._states.get(address)
            if state is None:
                state = PoolEventState(address=address)
                self._states[address] = state
            state.kind = str(entry.get("kind") or state.kind or "unknown")
            if tokens:
                if len(tokens) >= 1:
                    state.token0 = str(tokens[0])
                if len(tokens) >= 2:
                    state.token1 = str(tokens[1])
        if changed:
            self._address_version += 1
            self._wake.set()

    def prioritize_edges(
        self,
        edges: List[Any],
        *,
        current_block: int,
    ) -> Tuple[List[Any], Dict[str, Any]]:
        scored: List[Tuple[int, int, int, Any]] = []
        dirty_count = 0
        affected_tokens: set[str] = set()
        dirty_addresses: set[str] = set()
        for address, state in self._states.items():
            age = max(0, int(current_block) - int(state.last_block or 0))
            if address in self._dirty and int(state.last_block) and age <= 2:
                dirty_addresses.add(address)
                if state.token0:
                    affected_tokens.add(str(state.token0).lower())
                if state.token1:
                    affected_tokens.add(str(state.token1).lower())

        affected_subgraph_edges = 0
        for order, edge in enumerate(list(edges or [])):
            address = self._edge_pool_address(edge)
            priority = self.edge_priority(edge, current_block=int(current_block))
            state = self._states.get(address) if address else None
            last_block = int(state.last_block) if state is not None else 0
            edge_tokens = {
                str(getattr(edge, "token_in", "") or "").lower(),
                str(getattr(edge, "token_out", "") or "").lower(),
            }
            edge_tokens.discard("")
            if address in dirty_addresses:
                priority = max(priority, 5)
                dirty_count += 1
            elif affected_tokens and edge_tokens & affected_tokens:
                priority = max(priority, 4)
                affected_subgraph_edges += 1
            scored.append((priority, last_block, -order, edge))
        scored.sort(
            key=lambda item: (int(item[0]), int(item[1]), int(item[2])),
            reverse=True,
        )
        ordered = [item[3] for item in scored]
        return ordered, {
            "enabled": bool(self._tracked),
            "tracked_pools": int(len(self._tracked)),
            "tracked_states": int(sum(1 for state in self._states.values() if state.last_block)),
            "dirty_edges": int(dirty_count),
            "affected_token_count": int(len(affected_tokens)),
            "affected_subgraph_edges": int(affected_subgraph_edges),
            "last_event_block": int(self._last_seen_block),
            "event_count": int(self._event_count),
            "connected": bool(self._connected),
            "subscribed_address_count": int(self._subscribed_address_count),
            "subscription_truncated": bool(self._truncated),
            "last_error": str(self._last_error or ""),
            "candidate_generation_mode": str(
                self._last_candidate_metrics.get("candidate_generation_mode") or ""
            ),
            "candidate_edge_count": int(
                self._last_candidate_metrics.get("candidate_edge_count", 0) or 0
            ),
            "candidate_edges_full": int(
                self._last_candidate_metrics.get("candidate_edges_full", 0) or 0
            ),
            "candidate_edges_pruned": int(
                self._last_candidate_metrics.get("candidate_edges_pruned", 0) or 0
            ),
            "exploration_edge_count": int(
                self._last_candidate_metrics.get("exploration_edge_count", 0) or 0
            ),
            "hot_subgraph_edge_count": int(
                self._last_candidate_metrics.get("hot_subgraph_edge_count", 0) or 0
            ),
            "fresh_dirty_pool_count": int(
                self._last_candidate_metrics.get("fresh_dirty_pool_count", 0) or 0
            ),
        }

    def candidate_edges(
        self,
        edges: List[Any],
        *,
        current_block: int,
        max_candidates: int = 768,
        exploration_ratio: float = 0.10,
    ) -> Tuple[List[Any], Dict[str, Any]]:
        """Return a bounded event-driven hot subgraph plus exploration sample.

        Freshly changed pools define the hot token frontier. Every edge touching
        an affected token is retained, which preserves direct two-leg reverse
        pairs and one-hop triangle expansion. A deterministic exploration
        sample keeps the full graph from becoming permanently invisible when
        websocket events are incomplete or liquidity changes without an event
        we decode.
        """
        full = list(edges or [])
        cap = max(32, min(2048, int(max_candidates)))
        ratio = max(0.02, min(0.50, float(exploration_ratio)))

        fresh_dirty_pools: set[str] = set()
        affected_tokens: set[str] = set()
        for address, state in self._states.items():
            if address not in self._dirty or not int(state.last_block):
                continue
            age = max(0, int(current_block) - int(state.last_block))
            if age > 2:
                continue
            fresh_dirty_pools.add(address)
            if state.token0:
                affected_tokens.add(str(state.token0).lower())
            if state.token1:
                affected_tokens.add(str(state.token1).lower())

        if not fresh_dirty_pools:
            ordered, priority = self.prioritize_edges(
                full, current_block=int(current_block)
            )
            priority["candidate_generation_mode"] = "full_graph"
            priority["candidate_edge_count"] = int(len(ordered))
            priority["candidate_edges_pruned"] = 0
            priority["exploration_edge_count"] = 0
            self._last_candidate_metrics = dict(priority)
            return ordered, priority

        hot: List[Any] = []
        cold: List[Any] = []
        seen: set[str] = set()
        for edge in full:
            edge_id = self._edge_identity(edge)
            if edge_id in seen:
                continue
            seen.add(edge_id)
            address = self._edge_pool_address(edge)
            edge_tokens = {
                str(getattr(edge, "token_in", "") or "").lower(),
                str(getattr(edge, "token_out", "") or "").lower(),
            }
            edge_tokens.discard("")
            if address in fresh_dirty_pools or edge_tokens & affected_tokens:
                hot.append(edge)
            else:
                cold.append(edge)

        exploration_count = min(
            len(cold),
            max(8, int(round(len(full) * ratio))),
        )
        exploration: List[Any] = []
        if cold and exploration_count:
            stride = max(1, len(cold) // exploration_count)
            start = int(current_block) % len(cold)
            idx = start
            visited = 0
            while len(exploration) < exploration_count and visited < len(cold) * 2:
                exploration.append(cold[idx % len(cold)])
                idx += stride
                visited += 1
                if visited >= len(cold) and len(exploration) < exploration_count:
                    exploration.append(cold[visited % len(cold)])

        combined: List[Any] = []
        for edge in [*hot, *exploration]:
            if edge not in combined:
                combined.append(edge)

        # Hot state wins the cap; exploration fills the remainder.
        combined = combined[:cap]
        if not combined and full:
            combined = full[:cap]
        combined, priority = self.prioritize_edges(
            combined, current_block=int(current_block)
        )
        priority.update(
            {
                "candidate_generation_mode": "dirty_subgraph",
                "candidate_edge_count": int(len(combined)),
                "candidate_edges_full": int(len(full)),
                "candidate_edges_pruned": int(max(0, len(full) - len(combined))),
                "exploration_edge_count": int(
                    sum(1 for edge in exploration if edge in combined)
                ),
                "hot_subgraph_edge_count": int(len(hot)),
                "fresh_dirty_pool_count": int(len(fresh_dirty_pools)),
                "affected_token_count": int(len(affected_tokens)),
                "max_candidates": int(cap),
                "exploration_ratio": float(ratio),
            }
        )
        self._last_candidate_metrics = dict(priority)
        return combined, priority

    @staticmethod
    def _edge_identity(edge: Any) -> str:
        params = getattr(edge, "params", {}) or {}
        parts = (
            str(getattr(edge, "dex", "") or ""),
            str(getattr(edge, "venue", "") or ""),
            str(getattr(edge, "token_in", "") or ""),
            str(getattr(edge, "token_out", "") or ""),
            repr(sorted((str(k), str(v)) for k, v in dict(params).items())),
        )
        return "|".join(parts)

    def edge_priority(self, edge: Any, *, current_block: int) -> int:
        address = self._edge_pool_address(edge)
        if not address:
            return 1
        state = self._states.get(address)
        if state is None or not int(state.last_block):
            return 1
        age = max(0, int(current_block) - int(state.last_block))
        if address in self._dirty and age <= 2:
            return 4
        if age <= 2:
            return 3
        if age <= 5:
            return 2
        return 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "chain": str(self.chain_name),
            "chain_id": int(self.chain_id),
            "enabled": bool(self.ws_urls),
            "connected": bool(self._connected),
            "tracked_pools": int(len(self._tracked)),
            "tracked_states": int(sum(1 for state in self._states.values() if state.last_block)),
            "subscribed_address_count": int(self._subscribed_address_count),
            "subscription_truncated": bool(self._truncated),
            "last_event_block": int(self._last_seen_block),
            "event_count": int(self._event_count),
            "reconcile_count": int(self._reconcile_count),
            "reconcile_missed": int(self._reconcile_missed),
            "dirty_pool_count": int(len(self._dirty)),
            "last_message_ts": float(self._last_message_ts),
            "last_error": str(self._last_error or ""),
        }

    def state_for_pool(self, address: str) -> Optional[PoolEventState]:
        return self._states.get(str(address or "").strip().lower())

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():