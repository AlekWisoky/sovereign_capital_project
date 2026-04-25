from __future__ import annotations

from typing import Any, Dict, Iterable, List


def validate_multi_regime(*, candidate: Dict[str, Any], regimes: Iterable[str]) -> Dict[str, Any]:
    preferred = set(candidate.get("regime_tags") or [])
    scored = []
    passed = 0
    for r in list(regimes or []):
        fit = 1.0 if str(r) in preferred else 0.6
        robust = float(((candidate.get("stress_report") or {}).get("robustness_score") or 0.0))
        score = round((0.55 * fit) + (0.45 * robust), 6)
        ok = score >= 0.55
        passed += 1 if ok else 0
        scored.append({"regime": str(r), "score": score, "passed": ok})
    return {"passed": passed == len(scored), "coverage": scored, "passed_count": passed}
