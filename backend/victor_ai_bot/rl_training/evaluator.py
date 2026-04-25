from __future__ import annotations

from typing import Any, Dict


def evaluate_policy(
    *, reward: float, stability: float, max_failures: int, failures: int
) -> Dict[str, Any]:
    allowed = float(reward) > 0 and float(stability) >= 0.5 and int(failures) <= int(max_failures)
    return {"allowed": bool(allowed), "reason": "ok" if allowed else "policy_eval_failed"}
