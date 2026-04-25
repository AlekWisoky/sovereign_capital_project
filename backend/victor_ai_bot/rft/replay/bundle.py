from __future__ import annotations

import json
import os
from typing import Any, Dict, List


def _chain_dir(data_dir: str, chain: str | None = None) -> str:
    root = os.path.join(str(data_dir or ""), "rft", "replay")
    return os.path.join(root, str(chain)) if chain else root


def list_replay_bundles(data_dir: str, *, chain: str | None = None) -> List[str]:
    root = _chain_dir(data_dir, chain)
    out: List[str] = []
    if not os.path.exists(root):
        return out
    for base, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".json") and f != "tx_index.json":
                out.append(os.path.join(base, f))
    return out


def load_replay_bundle(data_dir: str, event_id: str) -> Dict[str, Any] | None:
    root = _chain_dir(data_dir)
    if not os.path.exists(root):
        return None
    for base, _dirs, files in os.walk(root):
        target = f"{str(event_id or '')}.json"
        if target in files:
            path = os.path.join(base, target)
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def export_replay_bundle(data_dir: str, event_id: str, out_path: str) -> Dict[str, Any]:
    bundle = load_replay_bundle(data_dir, event_id)
    if bundle is None:
        raise FileNotFoundError(f"replay bundle not found: {event_id}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, sort_keys=True)
    return bundle
