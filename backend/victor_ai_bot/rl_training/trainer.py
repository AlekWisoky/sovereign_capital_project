from __future__ import annotations

from typing import Any, Dict, Iterable

from .env import OfflineTradingEnv
from .reward import reward_function
from .policy_registry import PolicyRegistry
from .evaluator import evaluate_policy


def train_offline(
    *, samples: Iterable[Dict[str, Any]], family: str, registry: PolicyRegistry
) -> Dict[str, Any]:
    env = OfflineTradingEnv()
    env.reset()
    total = 0.0
    steps = 0
    last = {}
    for row in samples:
        rew = reward_function(
            realized_pnl=float((row or {}).get("realizedPnl", 0.0) or 0.0),
            capital_efficiency=float((row or {}).get("capitalEfficiency", 0.0) or 0.0),
            gas_efficiency=float((row or {}).get("gasEfficiency", 0.0) or 0.0),
            failure_rate=float((row or {}).get("failureRate", 0.0) or 0.0),
            stability=float((row or {}).get("stability", 0.5) or 0.0),
        )
        total += float(rew["reward"])
        steps += 1
        last = env.step(
            {
                "realizedPnl": row.get("realizedPnl", 0.0),
                "capitalEfficiency": row.get("capitalEfficiency", 0.0),
                "gasCost": row.get("gasCost", 0.0),
                "failures": row.get("failures", 0),
                "stability": row.get("stability", 0.5),
            }
        )
    avg = total / max(1, steps)
    ev = evaluate_policy(
        reward=avg,
        stability=float((last or {}).get("stability", 0.5) or 0.0),
        max_failures=3,
        failures=int((last or {}).get("failures", 0) or 0),
    )
    item = registry.add(
        policy_id=f"{family}-{steps}",
        family=family,
        reward=avg,
        status="sandbox" if ev["allowed"] else "retired",
    )
    return {"averageReward": round(avg, 6), "evaluation": ev, "policy": item}
