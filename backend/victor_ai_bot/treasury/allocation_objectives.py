from __future__ import annotations

from typing import Any, Dict


def allocation_objectives() -> Dict[str, Any]:
    return {
        "maximize": ["realized_pnl", "capital_efficiency", "stability"],
        "minimize": ["drawdown", "crowding", "failure_rate", "execution_cost"],
        "constraints": ["reserve_discipline", "stage_limits", "family_caps", "engine_caps"],
    }
