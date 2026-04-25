from __future__ import annotations

from typing import Any, Dict


def build_launch_summary(
    *, launch_state: Dict[str, Any], fund_summary: Dict[str, Any], engine_state: Dict[str, Any]
) -> Dict[str, Any]:
    families = list(launch_state.get("families") or [])
    active = [f for f in families if bool(f.get("active"))]
    blocked = {
        str(f.get("family")): (
            list(f.get("blockers") or f.get("reasons") or [""])[0]
            if list(f.get("blockers") or f.get("reasons") or [])
            else ""
        )
        for f in families
        if not bool(f.get("ready")) and not bool(f.get("active"))
    }
    return {
        "currentLaunchMode": str((launch_state.get("profile") or {}).get("mode") or "V1_ONLY"),
        "activeFamilies": [str(f.get("family")) for f in active],
        "nextRecommendedFamily": str(launch_state.get("recommended_next_family") or ""),
        "blockedFamilies": blocked,
        "fundStage": str((fund_summary or {}).get("fundStage") or ""),
        "engineCount": int(
            len(list(((engine_state or {}).get("summary") or {}).get("engines") or []))
        ),
        "rollbackRecommendation": str(
            ((launch_state.get("recommended_plan") or {}).get("rollback_recommendation") or "")
        ),
        "recommendedPlan": dict(launch_state.get("recommended_plan") or {}),
    }
