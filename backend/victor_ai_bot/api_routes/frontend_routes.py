from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import Any, Dict
import os

from ..jsonsafe import to_json_safe
from ..runtime_services.summary_read_contract import build_summary_read_contract
from ..runtime import MultiRuntimeBundle
from ..runtime_services.state_service import (
    apply_execution_gate_to_top_opportunity,
    apply_hold_to_top_opportunity,
    build_top_opportunity_view,
    select_top_opportunity,
    auto_trade_summary_projection,
    execution_advisory_info,
    execution_gate_info,
    summary_hold_info,
)

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(
        """<!doctype html><html><head><meta charset="utf-8"/><title>x∆v Admin</title>
<style>
body{background:#0b0f17;color:#e6edf3;font-family:ui-sans-serif,system-ui;margin:20px}
.card{background:#111827;border:1px solid #1f2937;border-radius:14px;padding:14px;margin-bottom:14px}
table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid #1f2937;padding:8px;text-align:left;font-size:13px}
.small{opacity:.8;font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid #1f2937;margin-left:8px;font-size:12px}
</style></head><body>
<h2>x∆v Admin <span class="badge" id="modes"></span></h2>
<div class="card"><div id="summary"></div></div>
<div class="card"><h3>Efficiency</h3><pre id="eff" class="small"></pre></div>
<div class="card"><h3>PnL Summary</h3><pre id="pnl" class="small"></pre></div>
<div class="card"><h3>RPC Health</h3><div id="rpc"></div></div>
<div class="card"><h3>Execution Log</h3><pre id="exec" class="small"></pre></div>
<div class="card"><h3>Errors</h3><pre id="errs" class="small"></pre></div>
<script>
async function tick(){
  const r = await fetch('/api/admin/state'); const j = await r.json();
  document.getElementById('modes').textContent = `send=${j.metrics.send_mode} gas=${j.metrics.gas_mode} auto=${j.settings?.auto_trading} reinvest=${j.settings?.auto_reinvest_enabled}:${j.settings?.reinvest_rate}%`;
  document.getElementById('summary').innerHTML =
    `<b>Chain:</b> ${j.chain} &nbsp; <b>Block:</b> ${j.metrics.last_block} &nbsp; <b>Scan:</b> ${j.metrics.scan_ms}ms &nbsp; <b>Opps:</b> ${(j.opportunities||[]).length}
     &nbsp; <b>Realized:</b> ${j.metrics.realized_profit_raw} &nbsp; <b>Eff%:</b> ${j.metrics.efficiency_pct.toFixed(2)} &nbsp; <b>SR%:</b> ${j.metrics.success_rate_pct.toFixed(2)}`;
  function renderTable(rows){
    let h = '<table><tr><th>url</th><th>ok</th><th>latency</th><th>failures</th><th>last_seen_block</th><th>score</th></tr>';
    for(const x of rows){ h += `<tr><td>${x.url}</td><td>${x.ok}</td><td>${x.latency_ms}</td><td>${x.failures}</td><td>${x.last_seen_block??''}</td><td>${x.score}</td></tr>`; }
    return h+'</table>';
  }
  document.getElementById('rpc').innerHTML = '<h4 class="small">Read</h4>'+renderTable(j.rpc.read)+'<h4 class="small">Send</h4>'+renderTable(j.rpc.send);
  document.getElementById('errs').textContent = (j.errors||[]).slice(-10).join('\n');
  document.getElementById('exec').textContent = JSON.stringify((j.exec_log||[]).slice(-20), null, 2);
  document.getElementById('eff').textContent = JSON.stringify(j.efficiency || {}, null, 2);
  document.getElementById('pnl').textContent = JSON.stringify(j.pnl_summary || {}, null, 2);
}
setInterval(tick, 2000); tick();
</script></body></html>"""
    )


@router.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    rt = websocket.app.state.runtime  # type: ignore
    # NOTE: /ws is legacy and must remain *active-chain only* without schema changes.
    # In multi-chain mode, bind this websocket to the currently active chain at connect time.
    if isinstance(rt, MultiRuntimeBundle):
        active = rt._active_chain
        q = rt._runtimes[active].subscribe()
    else:
        q = rt.subscribe()
    try:
        while True:
            msg = await q.get()
            # Never leak multi-chain wrapper fields on legacy /ws.
            if isinstance(msg, dict) and "chain" in msg:
                msg = {k: v for k, v in msg.items() if k != "chain"}
            await websocket.send_json(to_json_safe(msg))
    except WebSocketDisconnect:
        pass
    finally:
        try:
            if isinstance(rt, MultiRuntimeBundle):
                active = rt._active_chain
                rt._runtimes[active].unsubscribe(q)
            else:
                rt.unsubscribe(q)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass


@router.websocket("/ws/multichain")
async def ws_multichain(websocket: WebSocket):
    """Additive websocket that includes a top-level `chain` string.

    - If running MultiRuntimeBundle, events are already wrapped with `chain`.
    - If running a single RuntimeBundle, we inject `chain`.
    """
    await websocket.accept()
    rt = websocket.app.state.runtime  # type: ignore
    q = rt.subscribe()
    try:
        while True:
            msg = await q.get()
            if not isinstance(msg, dict):
                msg = {"type": "state", "data": msg}
            if "chain" not in msg:
                try:
                    msg["chain"] = getattr(rt.cfg.chain, "name", "")
                except AttributeError:
                    msg["chain"] = ""
            await websocket.send_json(to_json_safe(msg))
    except WebSocketDisconnect:
        pass
    finally:
        try:
            rt.unsubscribe(q)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass


@router.websocket("/ws/summary")
async def ws_summary(websocket: WebSocket):
    """Lightweight websocket for dashboards.

    Query params:
      - mode=summary|delta (default summary)
      - full_every=N (only for delta; send full summary every N messages)
    """
    await websocket.accept()
    mode = str(websocket.query_params.get("mode") or "summary").lower()
    try:
        full_every = int(str(websocket.query_params.get("full_every") or "10"))
    except (TypeError, ValueError):
        full_every = 10
    rt = websocket.app.state.runtime  # type: ignore
    q = rt.subscribe()
    last_summary: Dict[str, Any] | None = None
    counter = 0

    def _mk_summary(state_msg: Any) -> Dict[str, Any]:
        try:
            data = state_msg.get("data") if isinstance(state_msg, dict) else state_msg
            # state snapshot shape: {chain, opportunities, metrics, rpc, ...}
            chain = str(data.get("chain") or "")
            metrics = data.get("metrics") or {}
            opps = data.get("opportunities") or []
            execution_gate = execution_gate_info(rt)
            hold = summary_hold_info(rt, execution_gate)
            execution_advisory = execution_advisory_info(hold)
            opp_list = opps if isinstance(opps, list) else []
            top_candidate = select_top_opportunity(opp_list)
            top_info = apply_hold_to_top_opportunity(
                apply_execution_gate_to_top_opportunity(
                    build_top_opportunity_view(opp_list),
                    execution_gate,
                ),
                hold,
            )
            top_info, auto_trade_gate, auto_trade_recovery = auto_trade_summary_projection(
                rt,
                top_info,
                top_candidate,
            )
            capital_contract = rt.capital_contract() if hasattr(rt, "capital_contract") else {}
            capital_policy = rt.capital_policy() if hasattr(rt, "capital_policy") else {}
            summary_data = {
                "chain": chain,
                "block": metrics.get("last_block"),
                "scan_ms": metrics.get("scan_ms"),
                "opp_count": len(opps) if isinstance(opps, list) else 0,
                "metrics": {
                    "attempted": metrics.get("attempted"),
                    "succeeded": metrics.get("succeeded"),
                    "failed": metrics.get("failed"),
                    "flashLoans": metrics.get("flashLoans"),
                    "realized_profit_raw": metrics.get("realized_profit_raw"),
                    "efficiency_pct": metrics.get("efficiency_pct"),
                    "success_rate_pct": metrics.get("success_rate_pct"),
                    "gas_mode": metrics.get("gas_mode"),
                    "send_mode": metrics.get("send_mode"),
                },
                "top_opportunity": top_info,
                "execution_gate": execution_gate,
                "hold": hold,
                "execution_advisory": execution_advisory,
                "auto_trade_gate": auto_trade_gate,
                "auto_trade_recovery": auto_trade_recovery,
            }
            summary_data["summaryContract"] = build_summary_read_contract(
                family="frontend_runtime",
                payload=summary_data,
                capital_contract=capital_contract if isinstance(capital_contract, dict) else {},
                capital_policy=capital_policy if isinstance(capital_policy, dict) else {},
                phase="frontend_runtime_summary",
                read_model="frontend_runtime_summary_projection_v1",
            )
            return to_json_safe({"type": "summary", "data": summary_data})
        except (AttributeError, KeyError, TypeError, ValueError):
            return to_json_safe({"type": "summary", "data": {}})

    def _delta(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        """Shallow-ish delta: include only changed keys (recurses for dicts)."""
        out: Dict[str, Any] = {}
        for k, v in b.items():
            if k not in a:
                out[k] = v
            else:
                av = a.get(k)
                if isinstance(av, dict) and isinstance(v, dict):
                    d = _delta(av, v)
                    if d:
                        out[k] = d
                else:
                    if av != v:
                        out[k] = v
        return out

    try:
        while True:
            msg = await q.get()
            summary_msg = _mk_summary(msg)
            counter += 1
            if mode != "delta":
                await websocket.send_json(summary_msg)
                continue
            # delta mode
            current = summary_msg.get("data") if isinstance(summary_msg, dict) else None
            if not isinstance(current, dict):
                await websocket.send_json(summary_msg)
                continue
            if last_summary is None or full_every <= 1 or (counter % full_every == 0):
                await websocket.send_json(summary_msg)
                last_summary = current
                continue
            d = _delta(last_summary, current)
            # always include block
            d["block"] = current.get("block")
            await websocket.send_json(to_json_safe({"type": "delta", "data": d}))
            # update baseline
            last_summary = current
    except WebSocketDisconnect:
        pass
    finally:
        try:
            rt.unsubscribe(q)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass


@router.websocket("/ws/narrative")
async def ws_narrative(websocket: WebSocket):
    """Narrative stream websocket (additive).

    Auth:
      - If env VICTOR_ADMIN_KEY is set, pass ?key=... (or ?admin_key=...)
    """
    await websocket.accept()

    expected = os.environ.get("VICTOR_ADMIN_KEY", "").strip()
    if expected:
        got = str(
            websocket.query_params.get("key") or websocket.query_params.get("admin_key") or ""
        ).strip()
        if not got or got != expected:
            try:
                await websocket.close(code=4401)
            finally:
                return

    rt = websocket.app.state.runtime  # type: ignore
    if isinstance(rt, MultiRuntimeBundle):
        active = rt._active_chain
        q = rt._runtimes[active].narrative_subscribe()
    else:
        q = rt.narrative_subscribe() if hasattr(rt, "narrative_subscribe") else None

    if q is None:
        await websocket.send_json({"ok": False, "error": "narrative_unavailable"})
        await websocket.close(code=4404)
        return

    try:
        while True:
            msg = await q.get()
            await websocket.send_json(to_json_safe(msg))
    except WebSocketDisconnect:
        pass
    finally:
        try:
            if isinstance(rt, MultiRuntimeBundle):
                active = rt._active_chain
                rt._runtimes[active].narrative_unsubscribe(q)
            else:
                rt.narrative_unsubscribe(q)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
