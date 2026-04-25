from __future__ import annotations

from typing import Any, Dict


def reinvestment_policy(
    *, realized_profit_wei: int, aggressiveness_level: str, auto_reinvest_enabled: bool
) -> Dict[str, Any]:
    lvl = str(aggressiveness_level or "LOW").upper()
    if not auto_reinvest_enabled:
        reinvest = 0.35
    else:
        reinvest = 0.45 if lvl == "LOW" else (0.58 if lvl == "MODERATE" else 0.68)
    reserve = 0.30 if lvl == "LOW" else 0.22
    treasury = 0.20 if lvl == "LOW" else (0.15 if lvl == "MODERATE" else 0.10)
    governance = max(0.0, 1.0 - (reinvest + reserve + treasury))
    realized = max(0, int(realized_profit_wei))
    return {
        "reinvest_pct": reinvest,
        "reserve_pct": reserve,
        "treasury_pct": treasury,
        "governance_pct": governance,
        "reinvest_wei": int(realized * reinvest),
        "reserve_wei": int(realized * reserve),
        "treasury_wei": int(realized * treasury),
        "governance_wei": int(realized * governance),
    }
