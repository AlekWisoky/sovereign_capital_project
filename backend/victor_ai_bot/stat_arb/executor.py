from __future__ import annotations

from typing import Any, Dict

from .signals import zscore_signal
from .cointegration import cointegration_score
from ..execution_capture.universal_actions import UniversalAction


def build_pair_action(*, pair: tuple[str, str], spread_series: list[float], notional_usd: float) -> Dict[str, Any] | None:
    sig = zscore_signal(spread_series)
    if str(sig.get('signal')) == 'hold':
        return None
    coin = cointegration_score(spread_series, [-x for x in spread_series])
    conf = max(0.3, min(0.9, abs(float(sig.get('zscore') or 0.0))/3.0 + float(coin.get('score') or 0.0)/2.0))
    action = UniversalAction(action_id=f'statarb-{pair[0]}-{pair[1]}', family='stat_arb', action_type=str(sig.get('signal')), route_family='stat_arb', engine_type='stat_arb', chain='mixed', venues=['cex','dex'], token_path=[pair[0], pair[1]], expected_profit_usd=notional_usd*0.0025, expected_realized_profit_usd=notional_usd*0.0018, capital_required_usd=notional_usd, confidence=conf, lifecycle_stage='paper', metadata={'zscore': sig.get('zscore'), 'cointegration': coin.get('score')})
    return action.to_dict()
