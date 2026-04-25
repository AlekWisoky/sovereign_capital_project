from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any, Dict, List

from ..db import PersistenceDB

_SAFE_JSON_STATE_EXCEPTIONS = (JSONDecodeError, TypeError, ValueError)


def _loads_mapping(payload_json: Any) -> Dict[str, Any]:
    payload = json.loads(payload_json)
    if isinstance(payload, dict):
        return payload
    return {}


class EdgeModelRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    def upsert_prior(
        self,
        *,
        key: str,
        family: str,
        route_family: str,
        venue: str,
        lane: str,
        regime: str,
        payload: Dict[str, Any],
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO edge_model_priors(
                    chain,key,family,route_family,venue,lane,regime,count,success_ewma,competition_ewma,
                    quality_ewma,freshness_ewma,slippage_bias_ewma,failure_risk_ewma,updated_ts_ms,payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.chain,
                    key,
                    family,
                    route_family,
                    venue,
                    lane,
                    regime,
                    int(payload.get("count") or 0),
                    float(payload.get("success_ewma") or 0.0),
                    float(payload.get("competition_ewma") or 0.0),
                    float(payload.get("quality_ewma") or 0.0),
                    float(payload.get("freshness_ewma") or 0.0),
                    float(payload.get("slippage_bias_ewma") or 0.0),
                    float(payload.get("failure_risk_ewma") or 0.0),
                    int(payload.get("updated_ts_ms") or 0),
                    json.dumps(payload, sort_keys=True),
                ),
            )

    def get_prior(self, *, key: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM edge_model_priors WHERE chain=? AND key=?",
                (self.chain, key),
            ).fetchone()
        if row is None:
            return {}
        try:
            return _loads_mapping(row["payload_json"])
        except _SAFE_JSON_STATE_EXCEPTIONS:
            return {}

    def list_priors(self, *, family: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        sql = "SELECT payload_json FROM edge_model_priors WHERE chain=?"
        params: List[Any] = [self.chain]
        if family:
            sql += " AND family=?"
            params.append(family)
        sql += " ORDER BY updated_ts_ms DESC LIMIT ?"
        params.append(int(limit))
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                out.append(_loads_mapping(row["payload_json"]))
            except _SAFE_JSON_STATE_EXCEPTIONS:
                continue
        return out

    def insert_observation(
        self,
        *,
        family: str,
        route_family: str,
        venue: str,
        lane: str,
        regime: str,
        feature_json: Dict[str, Any],
        prediction_json: Dict[str, Any],
        outcome_json: Dict[str, Any],
        ts_ms: int,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO edge_model_observations(chain,family,route_family,venue,lane,regime,ts_ms,feature_json,prediction_json,outcome_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    self.chain,
                    family,
                    route_family,
                    venue,
                    lane,
                    regime,
                    int(ts_ms),
                    json.dumps(feature_json, sort_keys=True),
                    json.dumps(prediction_json, sort_keys=True),
                    json.dumps(outcome_json, sort_keys=True),
                ),
            )

    def recent_observations(
        self, *, family: str = "", route_family: str = "", limit: int = 200
    ) -> List[Dict[str, Any]]:
        sql = "SELECT family,route_family,venue,lane,regime,ts_ms,feature_json,prediction_json,outcome_json FROM edge_model_observations WHERE chain=?"
        params: List[Any] = [self.chain]
        if family:
            sql += " AND family=?"
            params.append(family)
        if route_family:
            sql += " AND route_family=?"
            params.append(route_family)
        sql += " ORDER BY ts_ms DESC LIMIT ?"
        params.append(int(limit))
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "family": row["family"],
                    "route_family": row["route_family"],
                    "venue": row["venue"],
                    "lane": row["lane"],
                    "regime": row["regime"],
                    "ts_ms": row["ts_ms"],
                    "features": json.loads(row["feature_json"]),
                    "prediction": json.loads(row["prediction_json"]),
                    "outcome": json.loads(row["outcome_json"]),
                }
            )
        return out
