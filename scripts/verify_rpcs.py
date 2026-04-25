#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import yaml

from victor_ai_bot.rpc import JsonRpcClient


@dataclass
class EndpointCheck:
    url: str
    kind: str
    ok: bool
    chain_id: Optional[int]
    block_number: Optional[int]
    latency_ms: int
    error: Optional[str] = None


async def _check(url: str, kind: str, *, timeout_s: float) -> EndpointCheck:
    t0 = time.perf_counter()
    try:
        async with JsonRpcClient(url, timeout_s=timeout_s, max_concurrency=4, max_batch=20) as rpc:
            chain_id = await rpc.chain_id()
            bn = await rpc.block_number()
        lat = int((time.perf_counter() - t0) * 1000)
        return EndpointCheck(url=url, kind=kind, ok=bool(chain_id) and bool(bn), chain_id=chain_id, block_number=bn, latency_ms=lat)
    except Exception as e:
        lat = int((time.perf_counter() - t0) * 1000)
        return EndpointCheck(url=url, kind=kind, ok=False, chain_id=None, block_number=None, latency_ms=lat, error=str(e))


def _dedupe(urls: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for u in urls:
        u = (u or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _load_from_cfg(path: str) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    chain = raw.get("chain") or {}
    read_urls = chain.get("rpc_read") or []
    send_urls = chain.get("rpc_send") or []
    private_urls = chain.get("rpc_private") or []
    if isinstance(read_urls, str):
        read_urls = [read_urls]
    if isinstance(send_urls, str):
        send_urls = [send_urls]
    if isinstance(private_urls, str):
        private_urls = [private_urls]
    return {
        "read": _dedupe(list(read_urls)),
        "send": _dedupe(list(send_urls) if send_urls else list(read_urls)),
        "private": _dedupe(list(private_urls)),
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description="Verify RPC endpoints (chainId, blockNumber, latency).")
    ap.add_argument("--config", default=os.environ.get("VICTOR_CONFIG", "backend/config/ethereum.yaml"))
    ap.add_argument("--configs", default=os.environ.get("VICTOR_MULTI_CONFIGS", ""),
                    help="Optional comma-separated list of configs to verify (multi-chain).")
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("VICTOR_RPC_VERIFY_TIMEOUT_S", "6")))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg_list: List[str] = []
    if args.configs:
        cfg_list = [x.strip() for x in args.configs.split(",") if x.strip()]
    if not cfg_list:
        cfg_list = [args.config]

    all_payloads: List[Dict[str, Any]] = []
    overall_ok = True
    for cfg_path in cfg_list:
        urls = _load_from_cfg(cfg_path)
        tasks: List[asyncio.Task] = []
        for kind, arr in urls.items():
            for u in arr:
                tasks.append(asyncio.create_task(_check(u, kind, timeout_s=args.timeout)))
        results = await asyncio.gather(*tasks)
        results = sorted(results, key=lambda r: (r.kind, r.latency_ms))
        ok_read = any(r.ok for r in results if r.kind == "read")
        ok_send = any(r.ok for r in results if r.kind == "send")
        ok_cfg = bool(ok_read and ok_send)
        overall_ok = overall_ok and ok_cfg
        all_payloads.append({
            "ok": ok_cfg,
            "config": cfg_path,
            "summary": {
                "read_ok": ok_read,
                "send_ok": ok_send,
                "private_count": sum(1 for r in results if r.kind == "private"),
            },
            "results": [r.__dict__ for r in results],
        })

    payload: Dict[str, Any] = {
        "ok": overall_ok,
        "configs": cfg_list,
        "checks": all_payloads,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for chk in all_payloads:
            print(f"config={chk['config']}")
            for r in chk["results"]:
                status = "OK" if r["ok"] else "FAIL"
                extra = f" chainId={r['chain_id']} block={r['block_number']}" if r["ok"] else f" error={r['error']}"
                print(f"[{r['kind']}] {status} {r['latency_ms']}ms {r['url']}{extra}")
            print(f"config_ok={chk['ok']}")
        print(f"overall_ok={payload['ok']}")

    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
