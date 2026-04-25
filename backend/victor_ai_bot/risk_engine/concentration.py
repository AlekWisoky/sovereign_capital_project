from __future__ import annotations

from typing import Any, Dict


def concentration_summary(
    *, capital_state: Dict[str, Any], engine_state: Dict[str, Any]
) -> Dict[str, Any]:
    cap = dict((capital_state or {}).get("capital_engine") or {})
    fam = dict(cap.get("family_targets") or {})
    engs = list((engine_state or {}).get("summary", {}).get("engines") or [])
    by_engine: Dict[str, float] = {}
    for item in engs:
        key = str(item.get("engine") or "unknown")
        by_engine[key] = by_engine.get(key, 0.0) + float(item.get("capitalShare") or 0.0)
    return {
        "familyTargets": fam,
        "engineConcentration": by_engine,
        "maxFamilyShare": max([float(v or 0.0) for v in fam.values()] + [0.0]),
        "maxEngineShare": max([float(v or 0.0) for v in by_engine.values()] + [0.0]),
    }
