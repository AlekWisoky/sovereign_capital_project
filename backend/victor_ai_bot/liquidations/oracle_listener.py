from __future__ import annotations

from typing import Any, Dict


def oracle_shock(signal: Dict[str, Any]) -> Dict[str, Any]:
    pct = abs(float((signal or {}).get('priceMovePct') or 0.0))
    return {'oracleShock': pct >= 2.0, 'priceMovePct': pct}
