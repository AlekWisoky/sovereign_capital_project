from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .config import GovernanceConfig
from .intent_schema import TransactionIntent


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def input_validation(*, meta: Dict[str, Any], cfg: GovernanceConfig) -> Dict[str, Any]:
    """Layer 1: Validate data feed integrity (heuristic).

    We do not have full market history here; instead we use conservative
    sanity checks on provided opportunity metrics.
    """

    mr = float(meta.get("margin_ratio", 0.0) or 0.0)
    gr = abs(float(meta.get("gas_ratio", 0.0) or 0.0))
    ps = float(meta.get("p_success", 0.0) or 0.0)

    # anomaly score in [0,1]
    anomaly = 0.0
    if mr > 0.02:  # 2% margin in atomic arb is suspiciously high
        anomaly += 0.35
    if gr > 0.01:
        anomaly += 0.35
    if ps < 0.40:
        anomaly += 0.25

    anomaly = float(_clip(anomaly, 0.0, 1.0))
    ok = anomaly < float(cfg.anomaly_score_limit)
    return {"ok": bool(ok), "anomaly_score": float(anomaly), "ts": int(time.time())}


def reasoning_guardrails(*, threat: Dict[str, Any], cfg: GovernanceConfig) -> Dict[str, Any]:
    """Layer 2: Reasoning guardrails.

    Uses threat monitor scores as inputs.
    """

    sev = float(threat.get("severity", 0.0) or 0.0)
    ok = sev < float(cfg.anomaly_score_limit)
    return {"ok": bool(ok), "severity": float(sev), "ts": int(time.time())}


def transaction_simulation_check(*, simulation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Layer 3: Transaction simulation check.

    The core engine already performs simulation when configured; we only
    interpret results here.
    """

    sim = dict(simulation or {})
    ok = bool(sim.get("ok", False)) if sim else True
    return {"ok": bool(ok), "ts": int(time.time()), "simulation": sim}


def run_security_stack(
    *,
    intent: TransactionIntent,
    meta: Dict[str, Any],
    threat: Dict[str, Any],
    simulation_result: Optional[Dict[str, Any]],
    cfg: GovernanceConfig,
) -> Dict[str, Any]:
    """Run layers 1-3; layers 4-5 are enforced in the core execution path."""

    # Hard rule: no aggressive profile without simulation.
    # We allow "scheduled" simulation if the core engine is configured to simulate
    # (dry-run or require_simulation). Callers can pass meta["will_simulate"]=True.
    if str(intent.risk_profile).lower() == "aggressive" and bool(
        getattr(cfg, "require_simulation_for_aggressive", True)
    ):
        if simulation_result is None and not bool(meta.get("will_simulate", False)):
            return {
                "ok": False,
                "reason": "aggressive_requires_sim",
                "ts": int(time.time()),
                "intent_id": str(intent.intent_id),
            }

    l1 = input_validation(meta=meta, cfg=cfg)
    l2 = reasoning_guardrails(threat=threat, cfg=cfg)
    l3 = transaction_simulation_check(simulation=simulation_result)

    ok = bool(l1.get("ok")) and bool(l2.get("ok")) and bool(l3.get("ok"))
    return {
        "ok": bool(ok),
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "ts": int(time.time()),
        "intent_id": str(intent.intent_id),
    }
