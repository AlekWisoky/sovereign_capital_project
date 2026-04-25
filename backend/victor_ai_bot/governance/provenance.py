from __future__ import annotations

from typing import Any, Dict


def provenance_record(*, source: str, owner: str, origin: str, notes: str = "") -> Dict[str, Any]:
    return {"source": str(source), "owner": str(owner), "origin": str(origin), "notes": str(notes)}
