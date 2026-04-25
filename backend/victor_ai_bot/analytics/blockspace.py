from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional


@dataclass
class BlockspaceIntel:
    """Blockspace Intelligence Dashboard.

    This is an analytics overlay (no execution authority).
    It maintains cheap, deterministic metrics for:
      - success rate by builder (best-effort)
      - gas premium heatmap (approx buckets)
      - competition density proxy
      - profit per gas spent
      - opportunity decay rate
    """

    window_blocks: int = 256
    _blocks: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=256))
    _exec: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=512))

    def observe_block(self, *, block: int, basefee_gwei: float, priority_gwei: float, pending_txs: int, mev_risk: float = 0.0, builder: str = "") -> None:
        self._blocks.append(
            {
                "ts": int(time.time()),
                "block": int(block),
                "basefee_gwei": float(basefee_gwei),
                "priority_gwei": float(priority_gwei),
                "pending_txs": int(pending_txs),
                "mev_risk": float(mev_risk),
                "builder": str(builder or ""),
            }
        )

    def observe_execution(self, *, tx_hash: str, ok: bool, profit_wei: int, gas_spent_wei: int, builder: str = "") -> None:
        self._exec.append(
            {
                "ts": int(time.time()),
                "tx_hash": str(tx_hash),
                "ok": bool(ok),
                "profit_wei": int(profit_wei),
                "gas_spent_wei": int(gas_spent_wei),
                "builder": str(builder or ""),
            }
        )

    def _bucket(self, x: float, *, edges: List[float]) -> str:
        for e in edges:
            if x <= e:
                return f"<= {e}"
        return f"> {edges[-1]}"

    def snapshot(self) -> Dict[str, Any]:
        blocks = list(self._blocks)
        execs = list(self._exec)
        # success by builder
        by_builder: Dict[str, Dict[str, int]] = {}
        for e in execs:
            b = str(e.get("builder") or "unknown")
            by_builder.setdefault(b, {"ok": 0, "n": 0})
            by_builder[b]["n"] += 1
            if bool(e.get("ok")):
                by_builder[b]["ok"] += 1
        success_by_builder = {b: (float(v["ok"]) / float(max(1, v["n"]))) for b, v in by_builder.items()}

        # gas premium heatmap (priority fee buckets)
        heat: Dict[str, int] = {}
        for b in blocks:
            pr = float(b.get("priority_gwei") or 0.0)
            k = self._bucket(pr, edges=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0])
            heat[k] = int(heat.get(k, 0)) + 1

        # competition density proxy
        comp = 0.0
        if blocks:
            avg_pending = sum(int(b.get("pending_txs") or 0) for b in blocks) / float(len(blocks))
            avg_mev = sum(float(b.get("mev_risk") or 0.0) for b in blocks) / float(len(blocks))
            comp = float(min(1.0, (avg_pending / 5000.0) * 0.6 + avg_mev * 0.4))

        # profit per gas spent
        ppg = 0.0
        gas_total = sum(int(e.get("gas_spent_wei") or 0) for e in execs)
        profit_total = sum(int(e.get("profit_wei") or 0) for e in execs)
        if gas_total > 0:
            ppg = float(profit_total) / float(gas_total)

        # opportunity decay proxy: opps per block trend
        decay = 0.0
        if len(blocks) >= 2:
            # derive from basefee slope as a crude proxy for decay (higher basefee -> fewer opps)
            bf0 = float(blocks[0].get("basefee_gwei") or 0.0)
            bf1 = float(blocks[-1].get("basefee_gwei") or 0.0)
            decay = float(min(1.0, max(0.0, (bf1 - bf0) / max(1.0, bf0))))

        return {
            "ts": int(time.time()),
            "window_blocks": int(self.window_blocks),
            "n_blocks": len(blocks),
            "n_exec": len(execs),
            "success_by_builder": success_by_builder,
            "gas_premium_heatmap": heat,
            "competition_density": float(comp),
            "profit_per_gas": float(ppg),
            "opportunity_decay": float(decay),
        }
