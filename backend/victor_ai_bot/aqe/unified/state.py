from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict

from .models import (
    UnifiedCapitalState,
    UnifiedDEXPoolState,
    UnifiedFundingData,
    UnifiedGasState,
    UnifiedMempoolState,
    UnifiedOrderBook,
    UnifiedPosition,
    asdict_safe,
)

_SAFE_NUMERIC_EXCEPTIONS = (TypeError, ValueError)
_SAFE_SNAPSHOT_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_BUS_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)


def _default_status() -> Dict[str, Any]:
    return {
        "input": "ok",
        "block": "ok",
        "gas": "ok",
        "mempool": "ok",
        "busMeta": "ok",
        "snapshot": "ok",
        "degraded": False,
    }


@dataclass
class UnifiedMarketState:
    """Normalized market state snapshot.

    This is a *foundation* for connector normalization, agent features, spread engines,
    dashboards and governance.

    It is updated best-effort; failures must not crash the core runtime.
    """

    chain: str = ""
    block: int = 0
    gas: UnifiedGasState = field(default_factory=UnifiedGasState)
    mempool: UnifiedMempoolState = field(default_factory=UnifiedMempoolState)
    capital: UnifiedCapitalState = field(default_factory=UnifiedCapitalState)

    # keyed collections
    orderbooks: Dict[str, UnifiedOrderBook] = field(default_factory=dict)  # venue|symbol
    funding: Dict[str, UnifiedFundingData] = field(default_factory=dict)  # venue|symbol
    positions: Dict[str, UnifiedPosition] = field(default_factory=dict)  # venue|symbol
    dex_pools: Dict[str, UnifiedDEXPoolState] = field(default_factory=dict)  # chain|venue|pool

    meta: Dict[str, Any] = field(default_factory=dict)
    status: Dict[str, Any] = field(default_factory=_default_status)

    def _refresh_degraded(self) -> None:
        self.status["degraded"] = any(
            self.status.get(key) != "ok"
            for key in ("input", "block", "gas", "mempool", "busMeta", "snapshot")
        )

    def _set_status(self, key: str, value: str) -> None:
        self.status[key] = str(value or "ok")
        self._refresh_degraded()

    def _reset_ingest_status(self) -> None:
        for key in ("input", "block", "gas", "mempool", "busMeta"):
            self.status[key] = "ok"
        self._refresh_degraded()

    @staticmethod
    def _safe_asdict(value: Any) -> tuple[Dict[str, Any], bool]:
        try:
            data = asdict(value)
        except _SAFE_SNAPSHOT_EXCEPTIONS:
            return {}, False
        return data if isinstance(data, dict) else {}, True

    @staticmethod
    def _serialize_mapping(values: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
        out: Dict[str, Any] = {}
        ok = True
        for key, value in values.items():
            try:
                out[str(key)] = asdict(value)
            except _SAFE_SNAPSHOT_EXCEPTIONS:
                ok = False
        return out, ok

    def update_block(self, *, chain: str, block: int) -> None:
        self.chain = str(chain or self.chain)
        self.block = int(block)

    def update_gas(
        self,
        *,
        basefee_gwei: float,
        priority_gwei: float = 0.0,
        max_fee_gwei: float = 0.0,
        congestion: float = 0.0,
    ) -> None:
        self.gas.basefee_gwei = float(basefee_gwei)
        self.gas.priority_gwei = float(priority_gwei)
        self.gas.max_fee_gwei = float(max_fee_gwei)
        self.gas.congestion = float(congestion)
        self.gas.ts = int(time.time())

    def update_mempool(
        self,
        *,
        pending_rate: float = 0.0,
        competition_density: float = 0.0,
        mev_risk: float = 0.0,
        builder_hint: str = "",
    ) -> None:
        self.mempool.pending_rate = float(pending_rate)
        self.mempool.competition_density = float(competition_density)
        self.mempool.mev_risk = float(mev_risk)
        self.mempool.builder_hint = str(builder_hint or "")
        self.mempool.ts = int(time.time())

    def upsert_orderbook(self, ob: UnifiedOrderBook) -> None:
        self.orderbooks[f"{ob.venue}|{ob.symbol}"] = ob

    def upsert_funding(self, fd: UnifiedFundingData) -> None:
        self.funding[f"{fd.venue}|{fd.symbol}"] = fd

    def upsert_position(self, pos: UnifiedPosition) -> None:
        self.positions[f"{pos.venue}|{pos.symbol}"] = pos

    def upsert_dex_pool(self, ps: UnifiedDEXPoolState) -> None:
        self.dex_pools[f"{ps.chain}|{ps.venue}|{ps.pool}"] = ps

    def ingest_bus_snapshot(self, snap: Dict[str, Any]) -> None:
        """Best-effort ingestion from the global BUS snapshot."""
        self._reset_ingest_status()
        if not isinstance(snap, dict):
            self._set_status("input", "snapshot_invalid")
            return
        try:
            block = int(snap.get("block") or self.block)
            chain = str(snap.get("chain") or self.chain)
            self.update_block(chain=chain, block=block)
        except _SAFE_BUS_EXCEPTIONS:
            self._set_status("block", "block_invalid")
        try:
            gas_parent = snap.get("gas")
            gas = (gas_parent or {}).get("data") if isinstance(gas_parent, dict) else gas_parent
            if isinstance(gas, dict):
                self.update_gas(
                    basefee_gwei=float(gas.get("basefee_gwei", self.gas.basefee_gwei) or 0.0),
                    priority_gwei=float(gas.get("priority_gwei", self.gas.priority_gwei) or 0.0),
                    max_fee_gwei=float(gas.get("max_fee_gwei", self.gas.max_fee_gwei) or 0.0),
                    congestion=float(gas.get("congestion", self.gas.congestion) or 0.0),
                )
        except _SAFE_NUMERIC_EXCEPTIONS:
            self._set_status("gas", "gas_invalid")
        try:
            mev_parent = snap.get("mev")
            mev = (mev_parent or {}).get("data") if isinstance(mev_parent, dict) else mev_parent
            if isinstance(mev, dict):
                self.update_mempool(
                    pending_rate=float(mev.get("pending_rate", self.mempool.pending_rate) or 0.0),
                    competition_density=float(
                        mev.get("competition_density", self.mempool.competition_density) or 0.0
                    ),
                    mev_risk=float(mev.get("mev_risk", self.mempool.mev_risk) or 0.0),
                    builder_hint=str(mev.get("builder", self.mempool.builder_hint) or ""),
                )
        except _SAFE_NUMERIC_EXCEPTIONS:
            self._set_status("mempool", "mempool_invalid")
        try:
            self.meta["bus"] = {str(key): asdict_safe(value) for key, value in snap.items()}
        except _SAFE_BUS_EXCEPTIONS:
            self.meta["bus"] = {}
            self._set_status("busMeta", "bus_meta_invalid")

    def snapshot(self) -> Dict[str, Any]:
        """JSON snapshot."""
        gas, gas_ok = self._safe_asdict(self.gas)
        mempool, mempool_ok = self._safe_asdict(self.mempool)
        capital, capital_ok = self._safe_asdict(self.capital)
        orderbooks, orderbooks_ok = self._serialize_mapping(self.orderbooks)
        funding, funding_ok = self._serialize_mapping(self.funding)
        positions, positions_ok = self._serialize_mapping(self.positions)
        dex_pools, dex_pools_ok = self._serialize_mapping(self.dex_pools)
        meta = dict(self.meta) if isinstance(self.meta, dict) else {}
        snapshot_ok = all(
            (
                gas_ok,
                mempool_ok,
                capital_ok,
                orderbooks_ok,
                funding_ok,
                positions_ok,
                dex_pools_ok,
            )
        )
        self._set_status("snapshot", "ok" if snapshot_ok else "snapshot_partial")
        return {
            "chain": self.chain,
            "block": int(self.block),
            "gas": gas,
            "mempool": mempool,
            "capital": capital,
            "orderbooks": orderbooks,
            "funding": funding,
            "positions": positions,
            "dex_pools": dex_pools,
            "meta": meta,
            "status": dict(self.status),
        }
