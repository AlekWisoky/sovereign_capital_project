from __future__ import annotations

from typing import Any, Dict, List

from ..db import PersistenceDB


class VenueRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    def upsert(self, venue: str, state: Dict[str, Any]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO venue_profiles(chain, venue, count, successes, failures, stale_quotes, total_slippage_bias, total_latency_ms, route_success_contribution) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    self.chain,
                    str(venue),
                    int(state.get("count") or 0),
                    int(state.get("successes") or 0),
                    int(state.get("failures") or 0),
                    int(state.get("stale_quotes") or 0),
                    float(state.get("total_slippage_bias") or 0.0),
                    float(state.get("total_latency_ms") or 0.0),
                    float(state.get("route_success_contribution") or 0.0),
                ),
            )

    def rows(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM venue_profiles WHERE chain = ? ORDER BY venue ASC", (self.chain,)
            ).fetchall()
        return [dict(r) for r in rows]
