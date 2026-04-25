from __future__ import annotations

import json
import os
import time
from typing import Any, Dict


class GovernanceAuditLog:
    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(data_dir, "governance", f"fund_audit_{chain}.jsonl")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def record(self, *, action: str, payload: Dict[str, Any]) -> None:
        row = {"ts": int(time.time()), "action": str(action), "payload": dict(payload or {})}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
