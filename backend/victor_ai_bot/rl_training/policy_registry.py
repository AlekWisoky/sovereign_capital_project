from __future__ import annotations

import json, os, time
from typing import Any, Dict, List


class PolicyRegistry:
    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(data_dir, "rl_training", f"policy_registry_{chain}.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            json.dump({"items": []}, open(self.path, "w", encoding="utf-8"), indent=2)

    def add(
        self, *, policy_id: str, family: str, reward: float, status: str = "sandbox"
    ) -> Dict[str, Any]:
        doc = json.load(open(self.path, "r", encoding="utf-8"))
        item = {
            "policyId": policy_id,
            "family": family,
            "reward": float(reward),
            "status": status,
            "ts": int(time.time()),
        }
        doc["items"].append(item)
        json.dump(doc, open(self.path, "w", encoding="utf-8"), indent=2, sort_keys=True)
        return item

    def items(self) -> List[Dict[str, Any]]:
        return list((json.load(open(self.path, "r", encoding="utf-8")) or {}).get("items") or [])
