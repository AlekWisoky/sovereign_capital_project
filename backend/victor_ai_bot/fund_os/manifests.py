from __future__ import annotations

from typing import Any, Dict

from .registry import FundOSRegistry
from .objectives import doctrine_snapshot
from .mandate_registry import fund_mandate_registry


def build_fund_manifest(stage: str = "internal_capital") -> Dict[str, Any]:
    reg = FundOSRegistry(stage=stage)
    return {
        "fund_os": {
            "stage_policy": reg.stage_policy(),
            "layers": reg.layer_manifest(),
            "capability_matrix": reg.capability_matrix(),
            "profit_doctrine": doctrine_snapshot(),
            "family_mandates": fund_mandate_registry(),
        }
    }
