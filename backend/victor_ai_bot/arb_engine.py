from __future__ import annotations
import time, hashlib, os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from .cache import PerBlockCache
from .models import Opportunity, Route, RouteLeg
from .quote_univ3 import quote_exact_input_single, quote_exact_input_single_batch
from .quote_curve import quote_curve, quote_curve_many
from .quote_balancer import quote_balancer_given_in, quote_balancer_given_in_many
from .gas_model import estimate_route_gas_units, estimate_gas_cost_wei_from_cfg
from .route_encoding import EncLeg, route_id_hex


_SAFE_EDGE_QUOTE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OverflowError,
    TypeError,
    ValueError,
)
_SAFE_POOL_KEY_EXCEPTIONS = (AttributeError, OverflowError, TypeError, ValueError)
_SAFE_AUX_DECODE_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_DYNAMIC_SLIPPAGE_EXCEPTIONS = (
    AttributeError,
    OverflowError,
    TypeError,
    ValueError,
    ZeroDivisionError,
)


def _aux_u256_to_b32_hex(n: int) -> str:
    return "0x" + (n & ((1 << 256) - 1)).to_bytes(32, "big").hex()


def aux_univ3_fee(fee: int) -> str:
    # low 24 bits
    return _aux_u256_to_b32_hex(int(fee) & 0xFFFFFF)


def aux_curve(i: int, j: int, underlying: bool) -> str:
    # low bits: i (8) | j (8) | underlying (1 at bit16)
    v = (int(i) & 0xFF) | ((int(j) & 0xFF) << 8) | ((1 if underlying else 0) << 16)
    return _aux_u256_to_b32_hex(v)


def aux_curve_from_meta(meta: Dict[str, Any], params: Dict[str, Any]) -> str:
    """Build Curve aux data from quote metadata when available.

    Important: quoting may use `get_dy_underlying` even if the configured edge
    is marked as non-underlying (or vice versa). The quote function records
    `used_underlying` and the i/j indices.
    """
    i = meta.get("i", params.get("i", 0))
    j = meta.get("j", params.get("j", 0))
    underlying = meta.get("used_underlying", params.get("underlying", False))
    return aux_curve(int(i), int(j), bool(underlying))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _id(parts: List[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _apply_slippage(amount: int, slippage_bps: int) -> int:
    return max(0, amount * (10_000 - slippage_bps) // 10_000)


@dataclass(frozen=True)
class Edge:
    dex: str
    venue: str
    token_in: str
    token_out: str
    params: Dict[str, Any]


async def quote_edge(
    rpc, cfg, cache: PerBlockCache, edge: Edge, amount_in: int
) -> Optional[Tuple[int, Dict[str, Any]]]:
    # cached per block per edge/amount
    ck = f"edge:{edge.dex}:{edge.venue}:{edge.token_in}:{edge.token_out}:{json_key(edge.params)}:{amount_in}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    out: Optional[Tuple[int, Dict[str, Any]]] = None
    try:
        if edge.dex == "univ3":
            fee = int(edge.params.get("fee", 3000))
            q = await quote_exact_input_single(
                rpc, cfg.chain.univ3_quoter_v2, edge.token_in, edge.token_out, fee, amount_in
            )
            if q:
                out = (q.amount_out, {"gas_estimate": q.gas_estimate, "fee": fee})
        elif edge.dex == "curve":
            pool = edge.venue
            i = int(edge.params["i"])
            j = int(edge.params["j"])
            underlying = bool(edge.params.get("underlying", False))
            q = await quote_curve(rpc, pool, i, j, amount_in, prefer_underlying=underlying)
            if q:
                out = (q.amount_out, {"used_underlying": q.used_underlying, "i": i, "j": j})
        elif edge.dex == "balancer":
            pool_id = edge.params["pool_id"]
            q = await quote_balancer_given_in(
                rpc, cfg.chain.balancer_vault, pool_id, edge.token_in, edge.token_out, amount_in
            )
            if q:
                out = (q.amount_out, {"pool_id": pool_id})
    except _SAFE_EDGE_QUOTE_EXCEPTIONS:
        out = None
    cache.set(ck, out)
    return out


def json_key(d: Dict[str, Any]) -> str:
    # stable key without importing json module (avoid overhead)
    items = sorted((str(k), str(v)) for k, v in d.items())
    return ",".join([f"{k}={v}" for k, v in items])


def edge_key(e: Edge) -> str:
    return f"{e.dex}:{e.venue}:{e.token_in}:{e.token_out}:{json_key(e.params)}"


async def quote_edges_batch(
    rpc,
    cfg,
    cache: PerBlockCache,
    edges: List[Edge],
    amount_in: int,
) -> Dict[str, Optional[Tuple[int, Dict[str, Any]]]]:
    """Batch-quote many edges for the same amount_in.

    Highest-ROI speedup: many quote calls become a handful of batched JSON-RPC requests.

    Returns a mapping edge_key(edge) -> (amount_out, meta) or None
    """
    out: Dict[str, Optional[Tuple[int, Dict[str, Any]]]] = {}
    missing_univ3: List[Tuple[int, Edge]] = []
    missing_curve: List[Tuple[int, Edge]] = []
    missing_bal: List[Tuple[int, Edge]] = []

    # read cache first
    for idx, e in enumerate(edges):
        ek = edge_key(e)
        ck = f"edge:{e.dex}:{e.venue}:{e.token_in}:{e.token_out}:{json_key(e.params)}:{amount_in}"
        hit = cache.get(ck)
        if hit is not None:
            out[ek] = hit
            continue
        if e.dex == "univ3":
            missing_univ3.append((idx, e))
        elif e.dex == "curve":
            missing_curve.append((idx, e))
        elif e.dex == "balancer":
            missing_bal.append((idx, e))
        else:
            out[ek] = None

    # UniV3 batch
    if missing_univ3 and getattr(cfg.chain, "univ3_quoter_v2", ""):
        reqs = []
        order: List[Edge] = []
        for _, e in missing_univ3:
            fee = int(e.params.get("fee", 3000))
            reqs.append((e.token_in, e.token_out, fee, int(amount_in), 0))
            order.append(e)
        quotes = await quote_exact_input_single_batch(rpc, cfg.chain.univ3_quoter_v2, reqs)
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = f"edge:{e.dex}:{e.venue}:{e.token_in}:{e.token_out}:{json_key(e.params)}:{amount_in}"
            if q:
                val = (
                    int(q.amount_out),
                    {"gas_estimate": int(q.gas_estimate), "fee": int(e.params.get("fee", 3000))},
                )
                out[ek] = val
                cache.set(ck, val)
            else:
                out[ek] = None
                cache.set(ck, None)

    # Curve batch (two-stage underlying fallback inside quote_curve_many)
    if missing_curve:
        reqs = []
        order = []
        for _, e in missing_curve:
            pool = e.venue
            i = int(e.params.get("i", 0))
            j = int(e.params.get("j", 0))
            underlying = bool(e.params.get("underlying", False))
            reqs.append((pool, i, j, int(amount_in), underlying))
            order.append(e)
        quotes = await quote_curve_many(rpc, reqs)
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = f"edge:{e.dex}:{e.venue}:{e.token_in}:{e.token_out}:{json_key(e.params)}:{amount_in}"
            if q:
                val = (
                    int(q.amount_out),
                    {
                        "used_underlying": bool(q.used_underlying),
                        "i": int(e.params.get("i", 0)),
                        "j": int(e.params.get("j", 0)),
                    },
                )
                out[ek] = val
                cache.set(ck, val)
            else:
                out[ek] = None
                cache.set(ck, None)

    # Balancer batch
    if missing_bal and getattr(cfg.chain, "balancer_vault", ""):
        reqs = []
        order = []
        for _, e in missing_bal:
            pool_id = str(e.params.get("pool_id") or "")
            reqs.append((pool_id, e.token_in, e.token_out, int(amount_in)))
            order.append(e)
        quotes = await quote_balancer_given_in_many(rpc, cfg.chain.balancer_vault, reqs)
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = f"edge:{e.dex}:{e.venue}:{e.token_in}:{e.token_out}:{json_key(e.params)}:{amount_in}"
            if q:
                val = (int(q.amount_out), {"pool_id": str(e.params.get("pool_id") or "")})
                out[ek] = val
                cache.set(ck, val)
            else:
                out[ek] = None
                cache.set(ck, None)

    # ensure all are present
    for e in edges:
        ek = edge_key(e)
        out.setdefault(ek, None)
    return out


def build_edges(cfg, *, extra_v3_pairs: Optional[List[dict]] = None) -> List[Edge]:
    edges: List[Edge] = []
    if cfg.chain.univ3_quoter_v2:
        # For execution we prefer SwapRouter; for quoting we use QuoterV2.
        # Safe default: if swap router is missing, we keep venue as quoter and
        # runtime will mark can_execute=false.
        v3_exec_venue = cfg.chain.univ3_swap_router or cfg.chain.univ3_quoter_v2
        v3_pairs = list(cfg.chain.v3_pairs or [])
        if extra_v3_pairs:
            # Discovered pools are additive and bounded; scanner de-dupes below.
            v3_pairs.extend(list(extra_v3_pairs))
        for p in v3_pairs:
            edges.append(
                Edge(
                    "univ3",
                    v3_exec_venue,
                    p["token_in"],
                    p["token_out"],
                    {"fee": int(p.get("fee", 3000))},
                )
            )
            # auto reverse
            edges.append(
                Edge(
                    "univ3",
                    v3_exec_venue,
                    p["token_out"],
                    p["token_in"],
                    {"fee": int(p.get("fee", 3000))},
                )
            )
    if bool(getattr(cfg.flags, "enable_curve_autogen", True)):
        for p in cfg.chain.curve_pools:
            pool = p["pool"]
            edges.append(
                Edge(
                    "curve",
                    pool,
                    p.get("token_in", ""),
                    p.get("token_out", ""),
                    {
                        "i": int(p["i"]),
                        "j": int(p["j"]),
                        "underlying": bool(p.get("underlying", False)),
                    },
                )
            )
            edges.append(
                Edge(
                    "curve",
                    pool,
                    p.get("token_out", ""),
                    p.get("token_in", ""),
                    {
                        "i": int(p["j"]),
                        "j": int(p["i"]),
                        "underlying": bool(p.get("underlying", False)),
                    },
                )
            )
    if bool(getattr(cfg.flags, "enable_balancer_autogen", True)) and cfg.chain.balancer_vault:
        for p in cfg.chain.balancer_pools:
            edges.append(
                Edge(
                    "balancer",
                    cfg.chain.balancer_vault,
                    p["token_in"],
                    p["token_out"],
                    {"pool_id": p["pool_id"]},
                )
            )
            edges.append(
                Edge(
                    "balancer",
                    cfg.chain.balancer_vault,
                    p["token_out"],
                    p["token_in"],
                    {"pool_id": p["pool_id"]},
                )
            )
    # remove empty-token curve edges if unspecified
    edges = [e for e in edges if e.token_in and e.token_out]
    # de-dupe
    seen = set()
    out = []
    for e in edges:
        k = (e.dex, e.venue, e.token_in, e.token_out, tuple(sorted(e.params.items())))
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def _pool_keys_for_leg(
    dex: str, token_in: str, token_out: str, params: Dict[str, Any], aux_hex: str
) -> str:
    """Stable conflict key used by portfolio optimizer.

    Key must be protocol-specific and avoid over-conflating pools.
    - UniswapV3: (token0, token1, fee)
    - Curve: (pool, i, j, underlying)
    - Balancer: (pool_id)

    Note: we intentionally do not include SwapRouter address for UniV3.
    """
    try:
        if dex == "univ3":
            fee = int(params.get("fee", 3000))
            a = token_in.lower()
            b = token_out.lower()
            if a > b:
                a, b = b, a
            return f"univ3:{a}:{b}:{fee}"
        if dex == "curve":
            pool = str(params.get("pool") or params.get("venue") or "")
            i = int(params.get("i", 0))
            j = int(params.get("j", 0))
            u = 1 if bool(params.get("underlying", False)) else 0
            return f"curve:{pool.lower()}:{i}:{j}:{u}"
        if dex == "balancer":
            pid = str(params.get("pool_id") or aux_hex or "")
            return f"bal:{pid.lower()}"
    except _SAFE_POOL_KEY_EXCEPTIONS:
        return f"{dex}:{token_in.lower()}:{token_out.lower()}:{json_key(params)}"
    # fallback (worst-case): route-level uniqueness
    return f"{dex}:{token_in.lower()}:{token_out.lower()}:{json_key(params)}"


async def find_two_leg_opportunities(
    rpc,
    cfg,
    cache: PerBlockCache,
    block_number: int,
    *,
    amount_in: int,
    slippage_bps: int,
    time_budget_ms: int = 2000,
    max_opps: int = 50,
    extra_v3_pairs: Optional[List[dict]] = None,
) -> List[Opportunity]:
    t_start = time.perf_counter()
    edges = build_edges(cfg, extra_v3_pairs=extra_v3_pairs)
    # map reverse candidates by (token_in, token_out)
    by_pair: Dict[Tuple[str, str], List[Edge]] = {}
    for e in edges:
        by_pair.setdefault((e.token_in, e.token_out), []).append(e)

    opps: List[Opportunity] = []
    # Batch quote all first-leg edges at base amount (biggest ROI speedup)
    qmap1 = await quote_edges_batch(rpc, cfg, cache, edges, amount_in)
    for e1 in edges:
        if (time.perf_counter() - t_start) * 1000.0 > time_budget_ms:
            break
        # look for e2 that returns to start
        revs = by_pair.get((e1.token_out, e1.token_in), [])
        if not revs:
            continue
        q1 = qmap1.get(edge_key(e1))
        if not q1:
            continue
        out1, meta1 = q1
        # Batch quote all candidate second legs for this out1
        qmap2 = await quote_edges_batch(rpc, cfg, cache, revs, out1)
        for e2 in revs:
            if (time.perf_counter() - t_start) * 1000.0 > time_budget_ms:
                break
            q2 = qmap2.get(edge_key(e2))
            if not q2:
                continue
            out2, meta2 = q2
            gross_profit = out2 - amount_in
            # Route-level gas estimate (ranking-only)
            # We'll fill meta after aux construction; here keep gross filter.
            # Filter unprofitable routes unless explicitly debugging.
            if gross_profit <= 0 and os.environ.get("VICTOR_DEBUG_OPPS", "").strip() != "1":
                continue
            # min_outs for legs include slippage haircut
            min1 = _apply_slippage(out1, slippage_bps)
            min2 = _apply_slippage(out2, slippage_bps)

            # Executor aux data (bytes32)
            aux1 = "0x"
            if e1.dex == "univ3":
                aux1 = aux_univ3_fee(int(e1.params.get("fee", 3000)))
            elif e1.dex == "curve":
                aux1 = aux_curve_from_meta(meta1, e1.params)
            elif e1.dex == "balancer":
                aux1 = str(e1.params.get("pool_id") or "0x")

            aux2 = "0x"
            if e2.dex == "univ3":
                aux2 = aux_univ3_fee(int(e2.params.get("fee", 3000)))
            elif e2.dex == "curve":
                aux2 = aux_curve_from_meta(meta2, e2.params)
            elif e2.dex == "balancer":
                aux2 = str(e2.params.get("pool_id") or "0x")

            rid = route_id_hex(
                [
                    EncLeg(
                        dex=e1.dex,
                        venue=e1.venue,
                        token_in=e1.token_in,
                        token_out=e1.token_out,
                        aux=aux1,
                    ),
                    EncLeg(
                        dex=e2.dex,
                        venue=e2.venue,
                        token_in=e2.token_in,
                        token_out=e2.token_out,
                        aux=aux2,
                    ),
                ]
            )

            pool_keys = [
                _pool_keys_for_leg(
                    e1.dex,
                    e1.token_in,
                    e1.token_out,
                    {
                        "fee": meta1.get("fee", e1.params.get("fee", 3000)),
                        "pool": e1.venue,
                        **e1.params,
                    },
                    aux1,
                ),
                _pool_keys_for_leg(
                    e2.dex,
                    e2.token_in,
                    e2.token_out,
                    {
                        "fee": meta2.get("fee", e2.params.get("fee", 3000)),
                        "pool": e2.venue,
                        **e2.params,
                    },
                    aux2,
                ),
            ]
            opp_id = _id([cfg.chain.name, "2leg", rid, str(amount_in), str(block_number)])
            opps.append(
                Opportunity(
                    id=opp_id,
                    chain=cfg.chain.name,
                    strategy=f"two-leg:{e1.dex}->{e2.dex}",
                    expected_profit_raw=str(gross_profit),
                    expected_profit_usd="0",
                    route=Route(
                        legs=[
                            RouteLeg(
                                dex=e1.dex,
                                venue=e1.venue,
                                token_in=e1.token_in,
                                token_out=e1.token_out,
                                amount_in=str(amount_in),
                                min_out=str(min1),
                                data=aux1,
                            ),
                            RouteLeg(
                                dex=e2.dex,
                                venue=e2.venue,
                                token_in=e2.token_in,
                                token_out=e2.token_out,
                                amount_in=str(out1),
                                min_out=str(min2),
                                data=aux2,
                            ),
                        ]
                    ),
                    min_outs=[str(min1), str(min2)],
                    route_id=rid,
                    can_execute=False,  # upgraded by runtime after safety checks
                    created_at_ms=_now_ms(),
                    meta={
                        "out1": str(out1),
                        "out2": str(out2),
                        "leg1": meta1,
                        "leg2": meta2,
                        "route_type": "2leg",
                        "venues": [e1.dex, e2.dex],
                        "pool_keys": pool_keys,
                        "gas_estimate_units": str(
                            estimate_route_gas_units(
                                {"leg1": meta1, "leg2": meta2, "venues": [e1.dex, e2.dex]}
                            )
                        ),
                        "gas_cost_estimate_wei": str(
                            estimate_gas_cost_wei_from_cfg(
                                cfg,
                                estimate_route_gas_units(
                                    {"leg1": meta1, "leg2": meta2, "venues": [e1.dex, e2.dex]}
                                ),
                            )
                        ),
                        "profit_after_gas_estimate_wei": str(
                            int(gross_profit)
                            - int(
                                estimate_gas_cost_wei_from_cfg(
                                    cfg,
                                    estimate_route_gas_units(
                                        {"leg1": meta1, "leg2": meta2, "venues": [e1.dex, e2.dex]}
                                    ),
                                )
                            )
                        ),
                    },
                )
            )
            if len(opps) >= max_opps:
                break
        if len(opps) >= max_opps:
            break
    # rank by gross profit desc
    opps.sort(key=lambda o: int(o.expected_profit_raw), reverse=True)
    return opps


async def find_three_leg_opportunities(
    rpc,
    cfg,
    cache: PerBlockCache,
    block_number: int,
    *,
    amount_in: int,
    slippage_bps: int,
    time_budget_ms: int = 2200,
    max_opps: int = 40,
    extra_v3_pairs: Optional[List[dict]] = None,
) -> List[Opportunity]:
    """Triangle / 3-hop cycle search A->B->C->A.

    Performance safety:
    - time budget enforced
    - adjacency limited per token
    - no discovery here; pass extra_v3_pairs from DiscoveryManager
    """
    t_start = time.perf_counter()
    edges = build_edges(cfg, extra_v3_pairs=extra_v3_pairs)
    # adjacency: token_in -> edges
    adj: Dict[str, List[Edge]] = {}
    for e in edges:
        adj.setdefault(e.token_in, []).append(e)

    # cap per token to avoid combinatorial explosion
    max_edges_per_token = int(os.environ.get("VICTOR_MAX_EDGES_PER_TOKEN", "10"))
    for k in list(adj.keys()):
        adj[k] = adj[k][:max_edges_per_token]

    # quick lookup for final leg candidates
    by_pair: Dict[Tuple[str, str], List[Edge]] = {}
    for e in edges:
        by_pair.setdefault((e.token_in, e.token_out), []).append(e)

    opps: List[Opportunity] = []
    # Batch quote all edges for base amount_in (used for first leg)
    qmap1_3 = await quote_edges_batch(rpc, cfg, cache, edges, amount_in)

    # iterate first edge; use time budget
    for a_in, outs in adj.items():
        for e1 in outs:
            if (time.perf_counter() - t_start) * 1000.0 > time_budget_ms:
                break
            if e1.token_in != a_in:
                continue
            # quote leg1
            q1 = qmap1_3.get(edge_key(e1))
            if not q1:
                continue
            out1, meta1 = q1
            # second leg candidates from token_out
            e2_cands = [e2 for e2 in adj.get(e1.token_out, []) if e2.token_out != e1.token_in]
            qmap2_3 = await quote_edges_batch(rpc, cfg, cache, e2_cands, out1)
            for e2 in e2_cands:
                if (time.perf_counter() - t_start) * 1000.0 > time_budget_ms:
                    break
                q2 = qmap2_3.get(edge_key(e2))
                if not q2:
                    continue
                out2, meta2 = q2
                # final leg must return to start
                revs = by_pair.get((e2.token_out, e1.token_in), [])
                if not revs:
                    continue
                e3_cands = list(revs[:3])
                qmap3_3 = await quote_edges_batch(rpc, cfg, cache, e3_cands, out2)
                for e3 in e3_cands:
                    if (time.perf_counter() - t_start) * 1000.0 > time_budget_ms:
                        break
                    q3 = qmap3_3.get(edge_key(e3))
                    if not q3:
                        continue
                    out3, meta3 = q3
                    gross_profit = out3 - amount_in
                    if gross_profit <= 0 and os.environ.get("VICTOR_DEBUG_OPPS", "").strip() != "1":
                        continue

                    # slippage haircut
                    min1 = _apply_slippage(out1, slippage_bps)
                    min2 = _apply_slippage(out2, slippage_bps)
                    min3 = _apply_slippage(out3, slippage_bps)

                    def _aux_for(edge: Edge, meta: Dict[str, Any]) -> str:
                        if edge.dex == "univ3":
                            return aux_univ3_fee(int(meta.get("fee", edge.params.get("fee", 3000))))
                        if edge.dex == "curve":
                            return aux_curve_from_meta(meta, edge.params)
                        if edge.dex == "balancer":
                            return str(edge.params.get("pool_id") or "0x")
                        return "0x"

                    aux1 = _aux_for(e1, meta1)
                    aux2 = _aux_for(e2, meta2)
                    aux3 = _aux_for(e3, meta3)

                    rid = route_id_hex(
                        [
                            EncLeg(
                                dex=e1.dex,
                                venue=e1.venue,
                                token_in=e1.token_in,
                                token_out=e1.token_out,
                                aux=aux1,
                            ),
                            EncLeg(
                                dex=e2.dex,
                                venue=e2.venue,
                                token_in=e2.token_in,
                                token_out=e2.token_out,
                                aux=aux2,
                            ),
                            EncLeg(
                                dex=e3.dex,
                                venue=e3.venue,
                                token_in=e3.token_in,
                                token_out=e3.token_out,
                                aux=aux3,
                            ),
                        ]
                    )

                    pool_keys = [
                        _pool_keys_for_leg(
                            e1.dex,
                            e1.token_in,
                            e1.token_out,
                            {
                                "fee": meta1.get("fee", e1.params.get("fee", 3000)),
                                "pool": e1.venue,
                                **e1.params,
                            },
                            aux1,
                        ),
                        _pool_keys_for_leg(
                            e2.dex,
                            e2.token_in,
                            e2.token_out,
                            {
                                "fee": meta2.get("fee", e2.params.get("fee", 3000)),
                                "pool": e2.venue,
                                **e2.params,
                            },
                            aux2,
                        ),
                        _pool_keys_for_leg(
                            e3.dex,
                            e3.token_in,
                            e3.token_out,
                            {
                                "fee": meta3.get("fee", e3.params.get("fee", 3000)),
                                "pool": e3.venue,
                                **e3.params,
                            },
                            aux3,
                        ),
                    ]

                    opp_id = _id([cfg.chain.name, "3leg", rid, str(amount_in), str(block_number)])
                    opps.append(
                        Opportunity(
                            id=opp_id,
                            chain=cfg.chain.name,
                            strategy=f"tri:{e1.dex}->{e2.dex}->{e3.dex}",
                            expected_profit_raw=str(gross_profit),
                            expected_profit_usd="0",
                            route=Route(
                                legs=[
                                    RouteLeg(
                                        dex=e1.dex,
                                        venue=e1.venue,
                                        token_in=e1.token_in,
                                        token_out=e1.token_out,
                                        amount_in=str(amount_in),
                                        min_out=str(min1),
                                        data=aux1,
                                    ),
                                    RouteLeg(
                                        dex=e2.dex,
                                        venue=e2.venue,
                                        token_in=e2.token_in,
                                        token_out=e2.token_out,
                                        amount_in=str(out1),
                                        min_out=str(min2),
                                        data=aux2,
                                    ),
                                    RouteLeg(
                                        dex=e3.dex,
                                        venue=e3.venue,
                                        token_in=e3.token_in,
                                        token_out=e3.token_out,
                                        amount_in=str(out2),
                                        min_out=str(min3),
                                        data=aux3,
                                    ),
                                ]
                            ),
                            min_outs=[str(min1), str(min2), str(min3)],
                            route_id=rid,
                            can_execute=False,
                            created_at_ms=_now_ms(),
                            meta={
                                "out1": str(out1),
                                "out2": str(out2),
                                "out3": str(out3),
                                "leg1": meta1,
                                "leg2": meta2,
                                "leg3": meta3,
                                "route_type": "3leg",
                                "venues": [e1.dex, e2.dex, e3.dex],
                                "pool_keys": pool_keys,
                                "gas_estimate_units": str(
                                    estimate_route_gas_units(
                                        {
                                            "leg1": meta1,
                                            "leg2": meta2,
                                            "leg3": meta3,
                                            "venues": [e1.dex, e2.dex, e3.dex],
                                        }
                                    )
                                ),
                                "gas_cost_estimate_wei": str(
                                    estimate_gas_cost_wei_from_cfg(
                                        cfg,
                                        estimate_route_gas_units(
                                            {
                                                "leg1": meta1,
                                                "leg2": meta2,
                                                "leg3": meta3,
                                                "venues": [e1.dex, e2.dex, e3.dex],
                                            }
                                        ),
                                    )
                                ),
                                "profit_after_gas_estimate_wei": str(
                                    int(gross_profit)
                                    - int(
                                        estimate_gas_cost_wei_from_cfg(
                                            cfg,
                                            estimate_route_gas_units(
                                                {
                                                    "leg1": meta1,
                                                    "leg2": meta2,
                                                    "leg3": meta3,
                                                    "venues": [e1.dex, e2.dex, e3.dex],
                                                }
                                            ),
                                        )
                                    )
                                ),
                            },
                        )
                    )
                    if len(opps) >= max_opps:
                        break
                if len(opps) >= max_opps:
                    break
            if len(opps) >= max_opps:
                break
        if len(opps) >= max_opps:
            break

    opps.sort(key=lambda o: int(o.expected_profit_raw), reverse=True)
    return opps


async def requote_opportunity(
    rpc,
    cfg,
    cache: PerBlockCache,
    opp: Opportunity,
    *,
    new_amount_in: int,
    slippage_bps: int,
) -> Optional[Opportunity]:
    """Re-quote an existing route for a new borrow amount.

    This is used for borrow-sizing actions (RL) without increasing scan RPC load.
    It is only invoked for attempted trades.
    """
    if new_amount_in <= 0:
        return None
    legs = list(opp.route.legs or [])
    if not legs:
        return None

    def _decode_u256_b32(aux_hex: str) -> int:
        try:
            h = aux_hex[2:] if aux_hex.startswith("0x") else aux_hex
            b = bytes.fromhex(h.rjust(64, "0"))
            return int.from_bytes(b, "big")
        except _SAFE_AUX_DECODE_EXCEPTIONS:
            return 0

    edges: List[Edge] = []
    for lg in legs:
        params: Dict[str, Any] = {}
        if lg.dex == "univ3":
            v = _decode_u256_b32(lg.data or "0x")
            params["fee"] = int(v & 0xFFFFFF) or 3000
        elif lg.dex == "curve":
            v = _decode_u256_b32(lg.data or "0x")
            params["i"] = int(v & 0xFF)
            params["j"] = int((v >> 8) & 0xFF)
            params["underlying"] = bool((v >> 16) & 1)
        elif lg.dex == "balancer":
            params["pool_id"] = str(lg.data or "0x")
        edges.append(Edge(lg.dex, lg.venue, lg.token_in, lg.token_out, params))

    amount = int(new_amount_in)
    outs: List[int] = []
    metas: List[Dict[str, Any]] = []
    impact_bps_per_leg: List[int] = []
    applied_bps_per_leg: List[int] = []

    # Optional dynamic slippage model (preflight only).
    dyn = bool(getattr(getattr(cfg, "safety", None), "dynamic_slippage_enabled", False))
    probe_bps = (
        int(getattr(getattr(cfg, "safety", None), "dynamic_slippage_probe_bps", 0) or 0)
        if dyn
        else 0
    )
    impact_mult = float(
        getattr(getattr(cfg, "safety", None), "dynamic_slippage_impact_mult", 1.0) or 1.0
    )
    min_bps = int(getattr(getattr(cfg, "safety", None), "dynamic_slippage_min_bps", 0) or 0)
    max_bps = int(
        getattr(getattr(cfg, "safety", None), "dynamic_slippage_max_bps", slippage_bps)
        or slippage_bps
    )
    for e in edges:
        q = await quote_edge(rpc, cfg, cache, e, amount)
        if not q:
            return None
        out, meta = q

        leg_impact_bps = 0
        leg_slip_bps = int(slippage_bps)
        if dyn and probe_bps > 0 and int(amount) > 0 and int(out) > 0:
            try:
                amount_probe = int(amount * (10000 + probe_bps) // 10000)
                if amount_probe <= amount:
                    amount_probe = amount + 1
                q2 = await quote_edge(rpc, cfg, cache, e, int(amount_probe))
                if q2:
                    out_probe, _m2 = q2
                    out_probe_i = int(out_probe)
                    # impact ≈ 1 - (out_probe/amount_probe) / (out/amount)
                    num = int(out) * int(amount_probe) - int(out_probe_i) * int(amount)
                    den = int(out) * int(amount_probe)
                    if num > 0 and den > 0:
                        leg_impact_bps = int((num * 10000) // den)
            except _SAFE_DYNAMIC_SLIPPAGE_EXCEPTIONS:
                leg_impact_bps = 0

            try:
                leg_slip_bps = int(
                    round(float(slippage_bps) + float(leg_impact_bps) * float(impact_mult))
                )
                leg_slip_bps = max(int(min_bps), min(int(max_bps), int(leg_slip_bps)))
            except _SAFE_DYNAMIC_SLIPPAGE_EXCEPTIONS:
                leg_slip_bps = int(slippage_bps)

        outs.append(int(out))
        metas.append(meta)
        impact_bps_per_leg.append(int(leg_impact_bps))
        applied_bps_per_leg.append(int(leg_slip_bps))
        amount = int(out)

    out_final = outs[-1] if outs else 0
    if out_final <= 0:
        return None

    # Update opp in-place (safe: only used for the attempted execution).
    opp.route.legs[0].amount_in = str(new_amount_in)
    for i in range(len(legs)):
        if i == 0:
            opp.route.legs[i].amount_in = str(new_amount_in)
        else:
            opp.route.legs[i].amount_in = str(outs[i - 1])
        bps_i = int(applied_bps_per_leg[i]) if i < len(applied_bps_per_leg) else int(slippage_bps)
        opp.route.legs[i].min_out = str(_apply_slippage(outs[i], bps_i))
    opp.min_outs = [
        str(
            _apply_slippage(
                outs[i],
                int(applied_bps_per_leg[i]) if i < len(applied_bps_per_leg) else int(slippage_bps),
            )
        )
        for i in range(len(outs))
    ]
    opp.expected_profit_raw = str(int(out_final) - int(new_amount_in))
    if isinstance(opp.meta, dict):
        # keep existing meta keys; update outs + leg metas.
        for i, out in enumerate(outs):
            opp.meta[f"out{i+1}"] = str(out)
            opp.meta[f"leg{i+1}"] = metas[i]
        opp.meta["requoted_amount_in"] = str(int(new_amount_in))
        opp.meta["slippage_model"] = {
            "dynamic": bool(dyn),
            "base_bps": int(slippage_bps),
            "probe_bps": int(probe_bps),
            "impact_mult": float(impact_mult),
            "impact_bps_per_leg": [int(x) for x in impact_bps_per_leg],
            "applied_bps_per_leg": [int(x) for x in applied_bps_per_leg],
        }
    return opp
