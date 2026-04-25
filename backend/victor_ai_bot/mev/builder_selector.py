from __future__ import annotations

from typing import Any, Dict, List


def pick_builder(builders: List[Dict[str, Any]]) -> Dict[str, Any]:
    ordered = sorted((dict(x) for x in builders), key=lambda r: (float(r.get('successRate', 0.0)), -float(r.get('latencyMs', 9999.0))), reverse=True)
    return ordered[0] if ordered else {'name': 'default-builder', 'successRate': 0.0, 'latencyMs': 9999.0}
