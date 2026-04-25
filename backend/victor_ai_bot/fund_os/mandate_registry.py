from __future__ import annotations

from typing import Any, Dict

from ..strategies.family_mandates import default_family_mandates


def fund_mandate_registry() -> Dict[str, Any]:
    return {"families": {k: v.to_dict() for k, v in default_family_mandates().items()}}
