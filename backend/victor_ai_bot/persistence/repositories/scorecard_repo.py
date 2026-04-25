from __future__ import annotations

import json
from typing import Any, Dict

from ..db import PersistenceDB


class FamilyScorecardRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    def upsert(self, family: str, state: Dict[str, Any]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO family_scorecards(chain,family,count,realized_pnl_usd,gas_cost_usd,successes,drawdown_penalty,correlation_penalty,regimes_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    self.chain,
                    str(family),
                    int(state.get("count") or 0),
                    float(state.get("realizedPnlUsd") or 0.0),
                    float(state.get("gasCostUsd") or 0.0),
                    int(state.get("successes") or 0),
                    float(state.get("drawdownPenalty") or 0.0),
                    float(state.get("correlationPenalty") or 0.0),
                    json.dumps(state.get("regimes") or {}, sort_keys=True),
                ),
            )

    def snapshot(self) -> Dict[str, Any]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM family_scorecards WHERE chain = ? ORDER BY family ASC", (self.chain,)
            ).fetchall()
        out = []
        for row in rows:
            count = int(row["count"] or 0)
            realized = float(row["realized_pnl_usd"] or 0.0)
            gas = float(row["gas_cost_usd"] or 0.0)
            out.append(
                {
                    "family": row["family"],
                    "count": count,
                    "realizedPnlUsd": round(realized, 6),
                    "stability": round(float(row["successes"] or 0) / max(1, count), 6),
                    "drawdownPenaltyUsd": round(float(row["drawdown_penalty"] or 0.0), 6),
                    "gasEfficiency": round(realized / max(1.0, gas), 6),
                    "executionSuccessRate": round(float(row["successes"] or 0) / max(1, count), 6),
                    "regimeDependence": {
                        k: int((v or {}).get("count") or 0) if isinstance(v, dict) else int(v or 0)
                        for k, v in json.loads(row["regimes_json"] or "{}").items()
                    },
                    "regimePerformance": {
                        k: {
                            "count": int((v or {}).get("count") or 0),
                            "pnlUsd": round(float((v or {}).get("pnlUsd") or 0.0), 6),
                            "successRate": round(
                                float((v or {}).get("successes") or 0)
                                / max(1, int((v or {}).get("count") or 0)),
                                6,
                            ),
                            "gasEfficiency": round(
                                float((v or {}).get("pnlUsd") or 0.0)
                                / max(1.0, float((v or {}).get("gasUsd") or 0.0)),
                                6,
                            ),
                        }
                        for k, v in json.loads(row["regimes_json"] or "{}").items()
                        if isinstance(v, dict)
                    },
                    "correlationPenalty": round(float(row["correlation_penalty"] or 0.0), 6),
                }
            )
        return {"families": out}
