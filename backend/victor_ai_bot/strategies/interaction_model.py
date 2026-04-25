from __future__ import annotations

from typing import Any, Dict, Iterable, List


def interaction_risk(
    *,
    family_a: str,
    family_b: str,
    tokens_a: Iterable[str],
    tokens_b: Iterable[str],
    venues_a: Iterable[str],
    venues_b: Iterable[str],
    chains_a: Iterable[str],
    chains_b: Iterable[str],
    shared_failure_mode: bool = False,
) -> Dict[str, Any]:
    ta = set(str(x) for x in list(tokens_a or []))
    tb = set(str(x) for x in list(tokens_b or []))
    va = set(str(x) for x in list(venues_a or []))
    vb = set(str(x) for x in list(venues_b or []))
    ca = set(str(x) for x in list(chains_a or []))
    cb = set(str(x) for x in list(chains_b or []))
    shared_tokens = len(ta & tb)
    shared_venues = len(va & vb)
    shared_chains = len(ca & cb)
    score = min(
        1.0,
        0.20 * shared_tokens
        + 0.18 * shared_venues
        + 0.10 * shared_chains
        + (0.25 if shared_failure_mode else 0.0)
        + (0.15 if family_a == family_b else 0.0),
    )
    return {
        "interaction_risk": round(score, 6),
        "shared_tokens": shared_tokens,
        "shared_venues": shared_venues,
        "shared_chains": shared_chains,
        "shared_failure_mode": bool(shared_failure_mode),
    }
