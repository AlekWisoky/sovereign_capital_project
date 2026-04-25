from __future__ import annotations

from typing import Any, Dict, List


def at_risk_accounts(rows: List[Dict[str, Any]], *, threshold: float = 1.02) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows if float((r or {}).get('healthFactor') or 99.0) <= float(threshold)]
