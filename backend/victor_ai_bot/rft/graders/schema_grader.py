from __future__ import annotations

from typing import Any, Dict

from pydantic import ValidationError

from ._common import ensure_proposal, make_component


def grade_schema(_ctx: Any, proposal: Dict[str, Any] | Any):
    try:
        parsed = ensure_proposal(proposal)
        return parsed, make_component("schema", +100, True, "valid_schema")
    except ValidationError as exc:
        return None, make_component("schema", -500, False, "invalid_schema", errors=exc.errors())
