from __future__ import annotations

"""Thin coordinator facade over the legacy runtime implementation.

This module centralizes the public runtime classes so `runtime.py` can stay a
true shell while the broader runtime migration continues safely.
"""

from ..runtime_legacy import *  # noqa: F401,F403
