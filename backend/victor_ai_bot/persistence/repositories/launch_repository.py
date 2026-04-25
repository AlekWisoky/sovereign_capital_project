from __future__ import annotations

import json
import os
from json import JSONDecodeError
from typing import Any, Dict

from ..db import PersistenceDB

_SAFE_JSON_STATE_EXCEPTIONS = (JSONDecodeError, TypeError, ValueError)
_SAFE_LAUNCH_FILE_LOAD_EXCEPTIONS = (OSError,) + _SAFE_JSON_STATE_EXCEPTIONS


def _loads_mapping(payload_json: Any) -> Dict[str, Any]:
    payload = json.loads(payload_json)
    if isinstance(payload, dict):
        return payload
    return {}


class LaunchRepository:
    def __init__(self, db: PersistenceDB, *, chain: str, path: str):
        self.db = db
        self.chain = str(chain)
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def save(self, payload: Dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO launch_state(chain,payload_json,updated_ts_ms) VALUES(?,?,?)",
                (
                    self.chain,
                    json.dumps(payload, sort_keys=True),
                    int(payload.get("updated_ts_ms") or 0),
                ),
            )

    def load(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    return _loads_mapping(f.read())
        except _SAFE_LAUNCH_FILE_LOAD_EXCEPTIONS:
            pass
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM launch_state WHERE chain=?", (self.chain,)
            ).fetchone()
        if row is None:
            return {}
        try:
            return _loads_mapping(row["payload_json"])
        except _SAFE_JSON_STATE_EXCEPTIONS:
            return {}
