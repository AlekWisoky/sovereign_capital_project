from __future__ import annotations

import json
import time
from typing import Any, Dict

from ..persistence.db import PersistenceDB


class SecurityAuditStore:
    def __init__(self, db: PersistenceDB):
        self.db = db

    def record(
        self,
        *,
        action: str,
        allowed: bool,
        capability: str,
        subject: str = "",
        chain: str = "",
        details: Dict[str, Any] | None = None,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO security_audit(ts_ms,action,subject,chain,allowed,capability,details_json) VALUES(?,?,?,?,?,?,?)",
                (
                    int(time.time() * 1000),
                    str(action),
                    str(subject),
                    str(chain),
                    1 if allowed else 0,
                    str(capability),
                    json.dumps(details or {}, sort_keys=True),
                ),
            )
