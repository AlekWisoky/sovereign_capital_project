from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_ROUTE_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def _runtime_bucket(*, ok: bool = True, code: str = "", detail: str = "") -> Dict[str, Any]:
    return {"ok": bool(ok), "code": str(code or ""), "detail": str(detail or "")}


def _init_runtime_state() -> Dict[str, Any]:
    return {
        "opp_route": _runtime_bucket(),
        "mev_state": _runtime_bucket(),
        "runtime_pending": _runtime_bucket(),
        "blockspace": _runtime_bucket(),
        "degraded": False,
    }


def _mark_runtime(state: Dict[str, Any], bucket: str, code: str, detail: str = "") -> None:
    state[bucket] = _runtime_bucket(ok=False, code=code, detail=detail)
    state["degraded"] = True


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except _SAFE_FLOAT_EXCEPTIONS:
        return default


def _unique(seq: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in list(seq or []):
        s = str(item or "")
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _legs_from_opp(opp: Any, runtime_state: Dict[str, Any]) -> List[Any]:
    try:
        route = getattr(opp, "route", None)
        raw_legs = getattr(route, "legs", []) or []
        return list(raw_legs)
    except _SAFE_ROUTE_EXCEPTIONS as exc:
        _mark_runtime(runtime_state, "opp_route", "pending_route_invalid", type(exc).__name__)
        return []


def _token_path_from_legs(legs: Sequence[Any], runtime_state: Dict[str, Any]) -> List[str]:
    if not legs:
        return []
    try:
        path: List[str] = []
        token_in = str(getattr(legs[0], "token_in") or "")
        if token_in:
            path.append(token_in)
        for leg in legs:
            token_out = str(getattr(leg, "token_out") or "")
            if token_out:
                path.append(token_out)
        return _unique(path)
    except _SAFE_ROUTE_EXCEPTIONS as exc:
        _mark_runtime(
            runtime_state,
            "opp_route",
            "pending_route_tokens_invalid",
            type(exc).__name__,
        )
        return []


def _venue_path_from_legs(legs: Sequence[Any], runtime_state: Dict[str, Any]) -> List[str]:
    try:
        return _unique(str(getattr(leg, "venue", "") or "") for leg in legs)
    except _SAFE_ROUTE_EXCEPTIONS as exc:
        _mark_runtime(
            runtime_state,
            "opp_route",
            "pending_route_venues_invalid",
            type(exc).__name__,
        )
        return []


def _safe_runtime_state_call(runtime: Any, attr: str, bucket: str, runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    method = getattr(runtime, attr, None)
    if method is None or not callable(method):
        return {}
    try:
        value = method() or {}
    except _SAFE_ROUTE_EXCEPTIONS as exc:
        _mark_runtime(runtime_state, bucket, f"pending_{bucket}_failed", type(exc).__name__)
        return {}
    if isinstance(value, dict):
        return dict(value)
    _mark_runtime(runtime_state, bucket, f"pending_{bucket}_invalid", type(value).__name__)
    return {}


def _safe_pending_map(runtime: Any, runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        pending_map = getattr(runtime, "_pending", {}) or {}
    except _SAFE_ROUTE_EXCEPTIONS as exc:
        _mark_runtime(runtime_state, "runtime_pending", "pending_runtime_pending_failed", type(exc).__name__)
        return {}
    if isinstance(pending_map, dict):
        return pending_map
    _mark_runtime(
        runtime_state,
        "runtime_pending",
        "pending_runtime_pending_invalid",
        type(pending_map).__name__,
    )
    return {}


def build_pending_state_context(
    *, runtime: Any, opp: Any, existing: Iterable[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    runtime_state = _init_runtime_state()
    legs = _legs_from_opp(opp, runtime_state)
    token_path = _token_path_from_legs(legs, runtime_state)
    pair = "/".join(token_path[:2]) if len(token_path) >= 2 else ""
    venues = _venue_path_from_legs(legs, runtime_state)
    route_family = str(
        ((getattr(opp, "meta", {}) or {}).get("route_family") or "")
        if isinstance(getattr(opp, "meta", None), dict)
        else ""
    )
    rows: List[Dict[str, Any]] = []
    seen = set()

    def add_row(row: Dict[str, Any], *, source: str) -> None:
        key = str(row.get("hash") or row.get("searcher_signature") or row.get("from") or "")
        if key and key in seen:
            return
        if key:
            seen.add(key)
        entry = dict(row)
        entry["source"] = source
        entry["tokens"] = _unique(list(entry.get("tokens") or []))
        entry["venues"] = _unique(list(entry.get("venues") or []))
        entry["pairs"] = _unique(list(entry.get("pairs") or []))
        entry["pool_keys"] = _unique(list(entry.get("pool_keys") or []))
        entry["route_family"] = str(entry.get("route_family") or route_family)
        entry["competition_relevance"] = round(
            min(
                1.0,
                max(
                    0.0,
                    0.35 * (1.0 if pair and pair in entry["pairs"] else 0.0)
                    + 0.25 * (1.0 if set(venues) & set(entry["venues"]) else 0.0)
                    + 0.20 * (1.0 if set(token_path) & set(entry["tokens"]) else 0.0)
                    + 0.20
                    * min(
                        1.0,
                        _safe_float(
                            entry.get("gas_price_pressure") or entry.get("priority") or 0.0
                        ),
                    ),
                ),
            ),
            6,
        )
        rows.append(entry)

    for row in list(existing or []):
        if isinstance(row, dict):
            add_row(row, source=str(row.get("source") or "existing"))

    mev = _safe_runtime_state_call(runtime, "mev_state", "mev_state", runtime_state)
    for row in list(mev.get("sample_pending") or [])[:12]:
        if not isinstance(row, dict):
            continue
        tags = [str(x) for x in list(row.get("tags") or []) if str(x)]
        add_row(
            {
                "hash": str(row.get("hash") or ""),
                "from": str(row.get("from") or ""),
                "tokens": token_path if any("token" in t for t in tags) else [],
                "venues": venues if any("dex" in t or "pool" in t for t in tags) else [],
                "pairs": [pair] if pair else [],
                "searcher_signature": str(row.get("from") or ""),
                "priority": _safe_float(row.get("prio_fee"), 0.0) / 1_000_000_000.0,
                "gas_price_pressure": min(
                    1.0, _safe_float(row.get("prio_fee"), 0.0) / 50_000_000_000.0
                ),
            },
            source="mev_sample",
        )

    pending_map = _safe_pending_map(runtime, runtime_state)
    for txh, pending in list(pending_map.items())[-20:]:
        row = dict(pending or {}) if isinstance(pending, dict) else {}
        add_row(
            {
                "hash": str(row.get("tx_hash") or txh or ""),
                "tokens": _unique(list(row.get("tokens") or [])) or token_path,
                "venues": _unique(list(row.get("venues") or [])) or venues,
                "pairs": _unique(list(row.get("pairs") or [])) or ([pair] if pair else []),
                "searcher_signature": str(row.get("from") or row.get("sender") or ""),
                "priority": _safe_float(
                    row.get("priority") or row.get("gas_price_pressure") or 0.0
                ),
                "gas_price_pressure": _safe_float(
                    row.get("gas_price_pressure") or row.get("priority") or 0.0
                ),
                "route_family": str(row.get("route_family") or route_family),
            },
            source="runtime_pending",
        )

    blockspace = _safe_runtime_state_call(
        runtime, "blockspace_state", "blockspace", runtime_state
    )
    pending_rate = _safe_float(
        (blockspace.get("summary") or {}).get("competition_pressure") or 0.0, 0.0
    )

    rows.sort(
        key=lambda x: (
            -float(x.get("competition_relevance") or 0.0),
            -float(x.get("priority") or 0.0),
            str(x.get("hash") or x.get("searcher_signature") or ""),
        )
    )
    rows = rows[:12]
    return {
        "rows": rows,
        "summary": {
            "pair": pair,
            "venues": venues,
            "tokens": token_path,
            "route_family": route_family,
            "pending_rate": round(pending_rate, 6),
            "sources": _unique(str(r.get("source") or "") for r in rows),
            "count": len(rows),
            "degraded": bool(runtime_state.get("degraded")),
        },
        "runtime": runtime_state,
    }
