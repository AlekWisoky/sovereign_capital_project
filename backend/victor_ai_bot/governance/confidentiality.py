from __future__ import annotations

from typing import Dict


_ALLOWED = {"internal_only", "restricted_pm", "operator_visible"}


def classify(level: str) -> Dict[str, str]:
    lvl = str(level or "internal_only")
    if lvl not in _ALLOWED:
        lvl = "internal_only"
    return {"confidentiality": lvl}
