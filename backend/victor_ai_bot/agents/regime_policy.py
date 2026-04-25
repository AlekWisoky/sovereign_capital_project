from __future__ import annotations

from typing import Dict

from .contracts import canonical_agent_name

_BASE = {
    'Ben Graham Agent': 1.10,
    'Bill Ackman Agent': 0.95,
    'Cathie Wood Agent': 0.90,
    'Charlie Munger Agent': 1.00,
    'Phil Fisher Agent': 0.95,
    'Stanley Druckenmiller Agent': 1.00,
    'Warren Buffett Agent': 1.05,
    'Valuation Agent': 1.00,
    'Sentiment Agent': 0.80,
    'Fundamentals Agent': 0.95,
    'Technicals Agent': 0.90,
    'Risk Manager': 1.20,
    'Portfolio Manager': 1.10,
}

_OVERRIDES = {
    'high_volatility': {
        'Stanley Druckenmiller Agent': 1.20,
        'Technicals Agent': 1.20,
        'Risk Manager': 1.30,
        'Bill Ackman Agent': 1.10,
        'Cathie Wood Agent': 0.90,
    },
    'low_volatility': {
        'Ben Graham Agent': 1.15,
        'Warren Buffett Agent': 1.15,
        'Charlie Munger Agent': 1.10,
        'Valuation Agent': 1.15,
        'Technicals Agent': 0.80,
    },
    'gas_spike': {
        'Risk Manager': 1.35,
        'Ben Graham Agent': 1.10,
        'Technicals Agent': 0.75,
        'Bill Ackman Agent': 0.90,
        'Cathie Wood Agent': 0.80,
    },
    'low_liquidity': {
        'Risk Manager': 1.40,
        'Charlie Munger Agent': 1.10,
        'Stanley Druckenmiller Agent': 1.10,
        'Technicals Agent': 0.85,
        'Sentiment Agent': 0.75,
    },
    'bull': {
        'Cathie Wood Agent': 1.20,
        'Phil Fisher Agent': 1.10,
        'Sentiment Agent': 1.10,
        'Risk Manager': 0.95,
    },
    'bear': {
        'Ben Graham Agent': 1.20,
        'Warren Buffett Agent': 1.15,
        'Risk Manager': 1.30,
        'Cathie Wood Agent': 0.80,
        'Sentiment Agent': 0.80,
    },
    'balanced': {},
}


def regime_weights(regime: str) -> Dict[str, float]:
    out = dict(_BASE)
    out.update(_OVERRIDES.get(str(regime or 'balanced'), {}))
    return out


def weight_for_agent(agent: str, regime: str) -> float:
    return float(regime_weights(regime).get(canonical_agent_name(agent), 1.0))
