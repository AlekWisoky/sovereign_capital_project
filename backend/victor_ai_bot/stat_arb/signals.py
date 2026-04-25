from __future__ import annotations

from typing import Any, Dict, List


def zscore_signal(spread_series: List[float]) -> Dict[str, Any]:
    if len(spread_series) < 2:
        return {'zscore': 0.0, 'signal': 'hold'}
    mean = sum(spread_series)/len(spread_series)
    var = sum((x-mean)**2 for x in spread_series)/max(1, len(spread_series)-1)
    std = var ** 0.5
    z = (spread_series[-1]-mean)/std if std > 0 else 0.0
    signal = 'short_spread' if z > 1.5 else 'long_spread' if z < -1.5 else 'hold'
    return {'zscore': round(z, 6), 'signal': signal}
