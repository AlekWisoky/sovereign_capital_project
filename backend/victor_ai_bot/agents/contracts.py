from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class AgentMandate:
    agent_id: str
    role: str
    input_schema: Dict[str, str]
    output_schema: Dict[str, str]
    ttl_ms: int
    reasoning_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


ALIASES: Dict[str, str] = {
    'ValuationAgent': 'Valuation Agent',
    'SentimentAgent': 'Sentiment Agent',
    'FundamentalsAgent': 'Fundamentals Agent',
    'TechnicalsAgent': 'Technicals Agent',
    'RiskAgent': 'Risk Manager',
    'RiskManagerAgent': 'Risk Manager',
    'PortfolioManager': 'Portfolio Manager',
    'PortfolioManagerAgent': 'Portfolio Manager',
}


MANDATES: Dict[str, AgentMandate] = {
    'Ben Graham Agent': AgentMandate(
        'Ben Graham Agent',
        'deep value / margin-of-safety arb filter; only backs thick-buffer dislocations',
        {'local': 'dict', 'dex': 'dict', 'cex': 'dict', 'treasury': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        5000,
        ['margin_of_safety', 'deep_value', 'gas_discipline'],
    ),
    'Bill Ackman Agent': AgentMandate(
        'Bill Ackman Agent',
        'event/catalyst specialist; surfaces bold catalyst-driven opportunities and forced-flow anomalies',
        {'local': 'dict', 'mev': 'dict', 'liq': 'dict', 'wallets': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        3500,
        ['catalyst', 'forced_flow', 'anomaly'],
    ),
    'Cathie Wood Agent': AgentMandate(
        'Cathie Wood Agent',
        'innovation/growth specialist; favors expanding opportunity sets in innovation-rich regimes',
        {'local': 'dict', 'dex': 'dict', 'mev': 'dict', 'treasury': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        3000,
        ['innovation', 'growth', 'opportunity_density'],
    ),
    'Charlie Munger Agent': AgentMandate(
        'Charlie Munger Agent',
        'quality compounding specialist; prefers simple durable routes with strong execution quality',
        {'local': 'dict', 'cex': 'dict', 'dex': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        3500,
        ['quality', 'durability', 'simplicity'],
    ),
    'Phil Fisher Agent': AgentMandate(
        'Phil Fisher Agent',
        'scuttlebutt / acceleration specialist; looks for strengthening flow and edge acceleration',
        {'local': 'dict', 'cex': 'dict', 'wallets': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        4000,
        ['acceleration', 'flow', 'scuttlebutt'],
    ),
    'Stanley Druckenmiller Agent': AgentMandate(
        'Stanley Druckenmiller Agent',
        'macro asymmetry specialist; sizes only when regime asymmetry supports it',
        {'local': 'dict', 'cex': 'dict', 'mev': 'dict', 'treasury': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        3500,
        ['macro_asymmetry', 'regime_shift', 'convexity'],
    ),
    'Warren Buffett Agent': AgentMandate(
        'Warren Buffett Agent',
        'quality/value specialist; backs reliable routes with durable execution economics',
        {'local': 'dict', 'dex': 'dict', 'cex': 'dict', 'rel': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        4500,
        ['durability', 'quality_value', 'reliability'],
    ),
    'Valuation Agent': AgentMandate(
        'Valuation Agent',
        'intrinsic value and fair-value dislocation calculator',
        {'local': 'dict', 'dex': 'dict', 'cex': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        5000,
        ['valuation_gap', 'intrinsic_value', 'dislocation'],
    ),
    'Sentiment Agent': AgentMandate(
        'Sentiment Agent',
        'market sentiment / flow overlay used to tilt conviction, timing, and lane choice',
        {'local': 'dict', 'dex': 'dict', 'cex': 'dict', 'sent': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        4000,
        ['flow_shift', 'liquidity_mood', 'sentiment'],
    ),
    'Fundamentals Agent': AgentMandate(
        'Fundamentals Agent',
        'structural and wallet-flow specialist used to filter weak underlying conditions',
        {'local': 'dict', 'wallets': 'dict', 'treasury': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        4500,
        ['structural_fit', 'wallet_flow', 'fundamentals'],
    ),
    'Technicals Agent': AgentMandate(
        'Technicals Agent',
        'timing and momentum specialist for entry/exit cadence',
        {'local': 'dict', 'cex': 'dict', 'mev': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        2500,
        ['timing_window', 'microstructure', 'momentum'],
    ),
    'Risk Manager': AgentMandate(
        'Risk Manager',
        'risk veto and position-limits specialist; can only downsize or reject, never force risk-on',
        {'local': 'dict', 'mev': 'dict', 'treasury': 'dict', 'rel': 'dict'},
        {'signal': 'float', 'confidence': 'float', 'reasoning': 'dict', 'estimated_value_contribution': 'float'},
        2000,
        ['risk_gate', 'tail_risk', 'position_limit'],
    ),
    'Portfolio Manager': AgentMandate(
        'Portfolio Manager',
        'final allocator/aggregator; combines specialist views into a portfolio-level execution bias without bypassing risk gates',
        {'agent_outputs': 'list', 'regime': 'str', 'treasury': 'dict'},
        {'portfolio_signal': 'float', 'portfolio_confidence': 'float', 'contrib': 'dict', 'weights_used': 'dict'},
        1500,
        ['consensus', 'allocation', 'portfolio_construction'],
    ),
}


def canonical_agent_name(agent_id: str) -> str:
    key = str(agent_id or '').strip()
    return ALIASES.get(key, key)


def mandate_for(agent_id: str) -> AgentMandate:
    agent = canonical_agent_name(agent_id)
    return MANDATES.get(agent, AgentMandate(agent, 'generic', {}, {}, 3000, ['generic']))


def all_mandates() -> Dict[str, Dict[str, Any]]:
    return {k: v.to_dict() for k, v in sorted(MANDATES.items())}
