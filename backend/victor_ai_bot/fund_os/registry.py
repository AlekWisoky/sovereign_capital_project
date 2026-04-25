from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .fund_stage import default_fund_stages
from .layers import default_layer_contracts


@dataclass
class FundOSRegistry:
    stage: str = "internal_capital"

    def layer_manifest(self) -> Dict[str, Any]:
        return {k: v.to_dict() for k, v in default_layer_contracts().items()}

    def stage_policy(self) -> Dict[str, Any]:
        stages = default_fund_stages()
        return stages.get(self.stage, stages["internal_capital"]).to_dict()

    def capability_matrix(self) -> Dict[str, Any]:
        st = self.stage_policy()
        return {
            "stage": st["stage"],
            "allowed_engine_classes": list(st["allowed_engine_classes"]),
            "max_deployable_pct": float(st["max_deployable_pct"]),
            "experimental_capital_share": float(st["experimental_capital_share"]),
            "operator_scope": st["operator_scope"],
            "reporting_strictness": st["reporting_strictness"],
        }
