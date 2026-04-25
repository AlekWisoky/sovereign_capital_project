from __future__ import annotations

from typing import Any, Dict, List


def parse_pending(tx_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(x) for x in tx_rows if float((x or {}).get('gasPriceGwei') or 0.0) > 0.0]
