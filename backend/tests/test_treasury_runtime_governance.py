from __future__ import annotations

import time

from victor_ai_bot.config import load_config
from victor_ai_bot.treasury.config import ProfitGoal, TreasuryConfig
from victor_ai_bot.treasury.runtime import TreasuryRuntime


def test_load_config_populates_treasury_max_aggressiveness_without_approval(tmp_path):
    cfg_file = tmp_path / "treasury.yaml"
    cfg_file.write_text(
        """
execution:
  treasury:
    enabled: true
    max_aggressiveness_without_approval: MODERATE
    allow_maximum: true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cfg = load_config(str(cfg_file))

    assert cfg.execution.treasury.enabled is True
    assert cfg.execution.treasury.max_aggressiveness_without_approval == "MODERATE"
    assert cfg.execution.treasury.allow_maximum is True


def test_load_config_defaults_kelly_disabled_when_omitted(tmp_path):
    cfg_file = tmp_path / "execution.yaml"
    cfg_file.write_text(
        """
execution:
  dry_run: true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cfg = load_config(str(cfg_file))

    assert cfg.execution.kelly_enabled is False

def test_compute_aggressiveness_clamps_maximum_when_maximum_is_not_allowed():
    rt = TreasuryRuntime(
        cfg=TreasuryConfig(
            enabled=True,
            allow_maximum=False,
            goal=ProfitGoal(
                target_return_percentage=50.0,
                time_horizon_seconds=1,
                risk_tolerance="aggressive",
                max_drawdown_pct=10.0,
            ),
        )
    )
    rt._started_ts = int(time.time())

    out = rt.compute_aggressiveness(
        realized_profit_wei=0,
        estimated_capital_wei=100,
        drawdown_pct=0.0,
        volatility_regime="balanced",
    )

    assert out["aggressiveness_level"] == "HIGH"
    assert out["aggressiveness_multiplier"] == 1.25


def test_governance_check_blocks_above_configured_auto_trade_limit_without_approval():
    rt = TreasuryRuntime(
        cfg=TreasuryConfig(
            enabled=True,
            allow_maximum=True,
            max_aggressiveness_without_approval="MODERATE",
        )
    )

    denied = rt.governance_check(aggressiveness_level="HIGH", approved_by_human=False)
    allowed = rt.governance_check(aggressiveness_level="HIGH", approved_by_human=True)

    assert denied == {"ok": False, "reason": "aggressiveness_requires_approval"}
    assert allowed == {"ok": True, "reason": "ok"}
