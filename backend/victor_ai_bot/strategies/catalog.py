from __future__ import annotations

from typing import Any, Dict

from .families import family_for


def annotate_strategy_metadata(*, strategy_name: str, regime: str) -> Dict[str, Any]:
    fam = family_for(strategy_name)
    allowed = str(regime) not in set(fam.disallowed_regimes)
    return {
        "family": fam.family,
        "assumptions": list(fam.assumptions),
        "preferred_regimes": list(fam.preferred_regimes),
        "disallowed_regimes": list(fam.disallowed_regimes),
        "risk_profile": fam.risk_profile,
        "capital_cap_pct": float(fam.capital_cap_pct),
        "execution_sensitivity": fam.execution_sensitivity,
        "confidence_requirement": float(fam.confidence_requirement),
        "regime_allowed": bool(allowed),
        "regime_fit": float(
            1.0 if str(regime) in set(fam.preferred_regimes) else (0.25 if not allowed else 0.65)
        ),
    }
