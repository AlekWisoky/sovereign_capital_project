from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from ..agents.base import AgentOutput
from ..core.actions import ActionSpec, normalize_dist


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class PortfolioManagerConfig:
    # base weights by agent name (can be overridden by env/config later)
    weights: Dict[str, float] = None
    bias_strength: float = 0.18  # how strongly portfolio signal biases the joint policy
    min_conf: float = 0.05

    def __post_init__(self) -> None:
        if self.weights is None:
            # Default: value + risk weighted slightly higher; sentiment lower by default.
            self.weights = {
                "Ben Graham Agent": 1.10,
                "Warren Buffett Agent": 1.10,
                "Charlie Munger Agent": 1.00,
                "Cathie Wood Agent": 0.85,
                "Phil Fisher Agent": 0.90,
                "Stanley Druckenmiller Agent": 1.00,
                "Bill Ackman Agent": 0.90,
                "Valuation Agent": 1.00,
                "Sentiment Agent": 0.60,
                "Fundamentals Agent": 0.80,
                "Technicals Agent": 0.80,
                "Risk Manager": 1.25,
            }


class PortfolioManager:
    """Aggregates agent signals using a weighted consensus model.

    Output:
      - `portfolio_signal` in [-1, +1] (risk-on/risk-off sizing intent)
      - `weights_used` and per-agent contributions
      - optional policy bias for action selection (additive; can be disabled)
    """

    def __init__(self, cfg: PortfolioManagerConfig | None = None):
        self.cfg = cfg or PortfolioManagerConfig()

    def aggregate(self, agent_outs: List[AgentOutput]) -> Dict[str, Any]:
        contrib: Dict[str, float] = {}
        weights_used: Dict[str, float] = {}
        s = 0.0
        wsum = 0.0
        for out in agent_outs or []:
            nm = str((out.info or {}).get("name") or "agent")
            w = float((self.cfg.weights or {}).get(nm, 1.0))
            c = float(_clip(float(getattr(out, "confidence", 0.0) or 0.0), self.cfg.min_conf, 1.0))
            sig = float(_clip(float(getattr(out, "signal", 0.0) or 0.0), -1.0, 1.0))
            v = w * c * sig
            contrib[nm] = float(v)
            weights_used[nm] = float(w)
            s += v
            wsum += abs(w * c)

        portfolio_signal = float(_clip(s / (wsum or 1.0), -1.0, 1.0))
        # a conservative consensus confidence: magnitude + participation
        participation = float(_clip(len(agent_outs or []) / 12.0, 0.0, 1.0))
        conf = float(_clip(0.20 + 0.65 * abs(portfolio_signal) * participation, 0.05, 1.0))

        return {
            "portfolio_signal": float(portfolio_signal),
            "portfolio_confidence": float(conf),
            "weights_used": weights_used,
            "contrib": contrib,
        }

    def bias_policy(self, *, joint_pi: Dict[str, float], actions: List[ActionSpec], portfolio_signal: float) -> Dict[str, float]:
        """Return a biased policy distribution (multiplicative + renorm).

        Positive signal slightly boosts higher size/borrow actions.
        Negative signal boosts more conservative actions.

        This is additive: it does not override core selection; it nudges.
        """
        sig = float(_clip(portfolio_signal, -1.0, 1.0))
        if abs(sig) < 1e-6:
            return dict(joint_pi or {})
        strength = float(_clip(self.cfg.bias_strength, 0.0, 0.50))
        out: Dict[str, float] = {}
        for a in actions:
            k = a.key()
            p = float((joint_pi or {}).get(k, 0.0) or 0.0)
            notional = float(a.size_mult) * float(a.borrow_mult)
            # map notional into [0,1] roughly
            n = _clip((notional - 0.75) / (2.0 - 0.75), 0.0, 1.0)
            # if sig>0 boost high n; if sig<0 boost low n
            bias = (n if sig > 0 else (1.0 - n))
            mult = 1.0 + strength * abs(sig) * (bias - 0.5) * 2.0
            out[k] = max(0.0, p * mult)
        return normalize_dist(out)
