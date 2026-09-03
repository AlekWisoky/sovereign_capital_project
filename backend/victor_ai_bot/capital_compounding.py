"""Compatibility shim for the canonical Treasury capital-compounding kernel."""

from .treasury.capital_compounding import resolve_profit_promotion

__all__ = ["resolve_profit_promotion"]
