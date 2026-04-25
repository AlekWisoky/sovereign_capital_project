from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from ...caq_kds.bus import BUS
from ...rpc import JsonRpcClient

from .mempool import MempoolMonitor
from .models import MEVConfig, MEVState, PendingTxSummary
from .sandwich import score_sandwich_risk, summarize_risk


_SAFE_PARSE_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)
_SAFE_BUS_UPDATE_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_LOOP_EXCEPTIONS = (asyncio.TimeoutError, OSError, RuntimeError, TypeError, ValueError)
_SAFE_SAMPLE_EXCEPTIONS = (AttributeError, TypeError, ValueError)


class MEVRuntime:
    """Best-effort mempool monitor + MEV risk estimator (defensive-first)."""

    def __init__(self, *, cfg: MEVConfig, ws_urls: List[str], rpc_http_url: str):
        self.cfg = cfg
        self._ws_urls = [u for u in (ws_urls or []) if isinstance(u, str) and u]
        self._rpc_url = rpc_http_url

        self._monitor: Optional[MempoolMonitor] = None
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

        self._pending: Dict[str, PendingTxSummary] = {}
        self._risk_hist: Deque[float] = deque(maxlen=2000)
        self._last_error: str = ""
        self._last_update_ts: float = 0.0
        self._last_bus_ts: float = 0.0

    def start(self) -> None:
        if not self.cfg.enabled:
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()

        ws_url = self._pick_ws()
        if not ws_url:
            self._last_error = "no_ws_url"
            return

        self._monitor = MempoolMonitor(
            ws_url=ws_url,
            sample_rate=float(self.cfg.sample_rate),
            max_queue=max(200, int(self.cfg.max_pending)),
            reconnect_backoff_s=float(self.cfg.reconnect_backoff_s),
        )
        self._monitor.start()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._monitor is not None:
            await self._monitor.stop()
        if self._task is not None:
            self._task.cancel()

    def _pick_ws(self) -> str:
        # Prefer explicitly configured URLs; otherwise none.
        if self._ws_urls:
            return self._ws_urls[0]
        return ""

    def _record_bus_snapshot(self) -> None:
        now = time.time()
        if (now - float(self._last_bus_ts)) <= 1.0:
            return
        p50, p90, high = summarize_risk(list(self._risk_hist))
        BUS.update(
            'mev',
            {
                'pending_rate': float(min(1.0, len(self._pending) / max(1.0, float(self.cfg.max_pending)))),
                'router_flow': float(high),
                'sandwich_risk': float(p90),
            },
        )
        self._last_bus_ts = now

    async def _loop(self) -> None:
        if self._monitor is None:
            return
        try:
            async with JsonRpcClient(self._rpc_url, timeout_s=8.0, max_concurrency=30) as rpc:
                async for h in self._monitor.iter_hashes():
                    if self._stop.is_set():
                        return
                    if not isinstance(h, str) or not h.startswith("0x"):
                        continue
                    if len(self._pending) >= int(self.cfg.max_pending):
                        oldest = next(iter(self._pending), None)
                        if oldest is not None:
                            self._pending.pop(oldest, None)

                    txd = await rpc.get_tx_by_hash(h)
                    if not txd:
                        continue
                    try:
                        summ = self._to_summary(h, txd)
                        r = score_sandwich_risk(summ, self.cfg)
                        summ.tags.extend(r.tags)
                        self._risk_hist.append(float(r.risk))
                        self._pending[h] = summ
                        self._last_update_ts = time.time()
                        try:
                            self._record_bus_snapshot()
                        except _SAFE_BUS_UPDATE_EXCEPTIONS:
                            pass
                    except _SAFE_PARSE_EXCEPTIONS as e:
                        self._last_error = f"parse_failed:{type(e).__name__}:{e}"
                        continue
        except asyncio.CancelledError:
            return
        except _SAFE_LOOP_EXCEPTIONS as e:
            self._last_error = f"mev_loop_failed:{type(e).__name__}:{e}"

    def _to_summary(self, h: str, txd: Dict[str, Any]) -> PendingTxSummary:
        def _hexint(x) -> int:
            if isinstance(x, str) and x.startswith("0x"):
                return int(x, 16)
            return 0

        to = str(txd.get("to") or "")
        frm = str(txd.get("from") or "")
        nonce = _hexint(txd.get("nonce")) if txd.get("nonce") is not None else None
        value = _hexint(txd.get("value"))
        gas = _hexint(txd.get("gas")) if txd.get("gas") is not None else None
        gas_price = _hexint(txd.get("gasPrice")) if txd.get("gasPrice") is not None else None
        max_fee = _hexint(txd.get("maxFeePerGas")) if txd.get("maxFeePerGas") is not None else None
        max_prio = _hexint(txd.get("maxPriorityFeePerGas")) if txd.get("maxPriorityFeePerGas") is not None else None
        inp = str(txd.get("input") or "0x")
        now = time.time()

        return PendingTxSummary(
            tx_hash=h,
            to=to,
            frm=frm,
            nonce=nonce,
            value_wei=value,
            max_fee_per_gas=max_fee,
            max_priority_fee_per_gas=max_prio,
            gas_price=gas_price,
            gas=gas,
            input_0x=inp,
            first_seen_ts=now,
            last_seen_ts=now,
        )

    def state(self) -> Dict[str, Any]:
        st = MEVState()
        st.enabled = bool(self.cfg.enabled)
        st.mode = str(self.cfg.mode)

        if self._monitor is None:
            st.connected = False
            st.ws_url = self._pick_ws() or ""
        else:
            st.connected = bool(self._monitor.status.connected)
            st.ws_url = str(self._monitor.status.ws_url)
            st.last_error = str(self._monitor.status.last_error or self._last_error)

        st.pending_count = int(len(self._pending))
        st.last_error = str(self._last_error or st.last_error)
        st.last_update_ts = float(self._last_update_ts)

        p50, p90, high = summarize_risk(list(self._risk_hist))
        st.sandwich_risk_p50 = p50
        st.sandwich_risk_p90 = p90
        st.high_risk_ratio = high

        sample: List[Dict[str, Any]] = []
        try:
            for k in list(self._pending.keys())[-20:][::-1]:
                tx = self._pending.get(k)
                if not tx:
                    continue
                sample.append(
                    {
                        "hash": tx.tx_hash,
                        "to": tx.to,
                        "from": tx.frm,
                        "value_wei": tx.value_wei,
                        "prio_fee": tx.max_priority_fee_per_gas,
                        "tags": list(tx.tags),
                        "sel": (tx.input_0x[:10] if tx.input_0x else "0x"),
                    }
                )
        except _SAFE_SAMPLE_EXCEPTIONS:
            pass
        st.sample_pending = sample

        return {
            "ok": True,
            **st.__dict__,
        }
