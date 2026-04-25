from __future__ import annotations

"""Compatibility API shell.

All live public routes now belong to dedicated ``api_routes`` modules. This
module remains only as an import-stable compatibility boundary for tests and
older imports that still reference ``victor_ai_bot.api``.
"""

from fastapi import APIRouter, Request

from .api_legacy import get_runtime as legacy_get_runtime

router = APIRouter()


def get_runtime(request: Request):
    return legacy_get_runtime(request)


__all__ = ["router", "get_runtime"]
