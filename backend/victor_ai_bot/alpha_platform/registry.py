from __future__ import annotations

from typing import Any, Dict

from .classification import default_alpha_classifications


def alpha_engine_registry() -> Dict[str, Any]:
    cls = default_alpha_classifications()
    by_engine: Dict[str, Any] = {}
    for family, obj in cls.items():
        rec = obj.to_dict()
        by_engine.setdefault(rec['engine_type'], {'engine_type': rec['engine_type'], 'families': []})['families'].append(rec)
    return {'families': {k: v.to_dict() for k, v in cls.items()}, 'engines': by_engine}
