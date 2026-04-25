from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class FundLayerContract:
    layer_id: str
    title: str
    purpose: str
    owners: List[str]
    inputs: List[str]
    outputs: List[str]
    governance: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
