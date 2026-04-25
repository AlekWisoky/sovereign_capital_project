from __future__ import annotations

from typing import Any, Dict


def crowding_check(
    *,
    current_allocations: Dict[str, Dict[str, float]],
    candidate_engine: str,
    candidate_family: str,
    candidate_chain: str,
    capital_share: float,
    caps: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    caps = dict(caps or {})
    engine_cap = float(caps.get("engine_cap", 0.35) or 0.35)
    family_cap = float(caps.get("family_cap", 0.45) or 0.45)
    chain_cap = float(caps.get("chain_cap", 0.60) or 0.60)
    engine_now = float(
        (current_allocations.get("engine") or {}).get(str(candidate_engine or ""), 0.0) or 0.0
    )
    family_now = float(
        (current_allocations.get("family") or {}).get(str(candidate_family or ""), 0.0) or 0.0
    )
    chain_now = float(
        (current_allocations.get("chain") or {}).get(str(candidate_chain or ""), 0.0) or 0.0
    )
    reasons = []
    allowed = True
    scale = 1.0
    if engine_now + capital_share > engine_cap:
        allowed = False
        reasons.append("engine_crowding_cap")
    if family_now + capital_share > family_cap:
        allowed = False
        reasons.append("family_crowding_cap")
    if chain_now + capital_share > chain_cap:
        allowed = False
        reasons.append("chain_crowding_cap")
    if allowed:
        return {"allow": True, "scale": scale, "reason_codes": ["ok"]}
    over = max(
        engine_now + capital_share - engine_cap,
        family_now + capital_share - family_cap,
        chain_now + capital_share - chain_cap,
    )
    scale = max(0.0, min(0.9, 1.0 - max(0.05, over)))
    return {"allow": scale > 0.15, "scale": scale, "reason_codes": reasons}
