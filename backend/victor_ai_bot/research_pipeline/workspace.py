from __future__ import annotations

import json
import os
import time
from json import JSONDecodeError
from typing import Any, Dict

from .candidates import CandidateStore


class ResearchWorkspace:
    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(data_dir, "research", f"workspace_{chain}.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._chain = chain
        self._store = CandidateStore(data_dir=data_dir, chain=chain)
        self._state = self._load()

    def _blank(self, *, include_notes_enabled: bool = True) -> Dict[str, Any]:
        out: Dict[str, Any] = {"chain": self._chain, "createdTs": int(time.time())}
        if include_notes_enabled:
            out["notesEnabled"] = True
        return out

    def _coerce_state(self, data: Any) -> Dict[str, Any]:
        base = self._blank(include_notes_enabled=False)
        if not isinstance(data, dict):
            base["notesEnabled"] = True
            return base

        chain = str(data.get("chain") or self._chain)
        created_ts_raw = data.get("createdTs")
        try:
            created_ts = max(0, int(created_ts_raw))
        except (TypeError, ValueError):
            created_ts = base["createdTs"]

        notes_enabled = data.get("notesEnabled")
        if isinstance(notes_enabled, bool):
            notes_flag = notes_enabled
        elif notes_enabled is None:
            notes_flag = True
        else:
            notes_flag = str(notes_enabled).strip().lower() in {"1", "true", "yes", "on"}

        out: Dict[str, Any] = {
            "chain": chain,
            "createdTs": created_ts,
            "notesEnabled": notes_flag,
        }

        notes = data.get("notes")
        if isinstance(notes, str):
            out["notes"] = notes

        owner = data.get("owner")
        if isinstance(owner, str) and owner.strip():
            out["owner"] = owner

        updated_ts = data.get("updatedTs")
        try:
            out["updatedTs"] = max(0, int(updated_ts))
        except (TypeError, ValueError):
            pass
        return out

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
        except (OSError, JSONDecodeError, ValueError):
            return self._blank(include_notes_enabled=False)
        return self._coerce_state(data)

    def snapshot(self) -> Dict[str, Any]:
        out = dict(self._state)
        out["pipelineCounts"] = self._store.pipeline_counts()
        out["throughput"] = self._store.throughput_metrics()
        return out
