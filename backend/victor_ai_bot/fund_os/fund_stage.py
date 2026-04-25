from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class FundStagePolicy:
    stage: str
    max_deployable_pct: float
    experimental_capital_share: float
    max_family_concentration: float
    max_engine_concentration: float
    allowed_engine_classes: List[str]
    reporting_strictness: str
    operator_scope: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_fund_stages() -> Dict[str, FundStagePolicy]:
    return {
        "internal_capital": FundStagePolicy(
            "internal_capital",
            0.35,
            0.12,
            0.45,
            0.40,
            ["arbitrage", "carry", "protective", "generated"],
            "light",
            "core_ops",
        ),
        "pilot_capital": FundStagePolicy(
            "pilot_capital",
            0.42,
            0.10,
            0.40,
            0.35,
            ["arbitrage", "carry", "protective", "generated", "rebalancing"],
            "light",
            "core_ops",
        ),
        "friends_family": FundStagePolicy(
            "friends_family",
            0.48,
            0.08,
            0.34,
            0.30,
            ["arbitrage", "carry", "protective", "generated", "rebalancing"],
            "medium",
            "ops_plus_pm",
        ),
        "private_fund": FundStagePolicy(
            "private_fund",
            0.55,
            0.06,
            0.30,
            0.26,
            ["arbitrage", "carry", "protective", "generated", "rebalancing", "tactical"],
            "high",
            "fund_ops",
        ),
        "institutional_scale": FundStagePolicy(
            "institutional_scale",
            0.62,
            0.04,
            0.24,
            0.22,
            ["arbitrage", "carry", "protective", "generated", "rebalancing", "tactical"],
            "very_high",
            "segmented",
        ),
    }
