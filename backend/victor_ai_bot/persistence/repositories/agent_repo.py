from __future__ import annotations

import json
from typing import Any, Dict, List

from ..db import PersistenceDB


class AgentAttributionRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    def append(self, row: Dict[str, Any]) -> None:
        contributors = list(row.get("contributors") or [])
        ts_ms = int(row.get("ts_ms") or row.get("ts") or 0)
        with self.db.connect() as conn:
            for contrib in contributors:
                payload = dict(contrib)
                payload.update(
                    {
                        "opportunity_id": str(row.get("opportunity_id") or ""),
                        "route_id": str(row.get("route_id") or ""),
                        "strategy_family": str(row.get("strategy_family") or ""),
                    }
                )
                conn.execute(
                    "INSERT INTO agent_attribution(chain,ts_ms,opportunity_id,route_id,strategy_family,agent,followed,realized_pnl_impact_usd,precision_hit,regime,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        self.chain,
                        ts_ms,
                        str(row.get("opportunity_id") or ""),
                        str(row.get("route_id") or ""),
                        str(row.get("strategy_family") or ""),
                        str(contrib.get("agent") or "unknown"),
                        1 if bool(contrib.get("followed")) else 0,
                        float(contrib.get("realized_pnl_impact_usd") or 0.0),
                        1 if bool(contrib.get("precision_hit")) else 0,
                        str(contrib.get("regime") or row.get("regime") or ""),
                        json.dumps(payload, sort_keys=True),
                    ),
                )

    def summary(self) -> Dict[str, Any]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT agent, COUNT(*) AS count, SUM(followed) AS followed, SUM(realized_pnl_impact_usd) AS pnl, SUM(precision_hit) AS hits FROM agent_attribution WHERE chain = ? GROUP BY agent ORDER BY pnl DESC, agent ASC",
                (self.chain,),
            ).fetchall()
        return {
            "agents": [
                {
                    "agent": row["agent"],
                    "count": int(row["count"] or 0),
                    "followRate": round(
                        float(row["followed"] or 0.0) / max(1, int(row["count"] or 0)), 6
                    ),
                    "precision": round(
                        float(row["hits"] or 0.0) / max(1, int(row["count"] or 0)), 6
                    ),
                    "realizedImpactUsd": round(float(row["pnl"] or 0.0), 6),
                }
                for row in rows
            ]
        }
