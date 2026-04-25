from __future__ import annotations

import json
import os
from typing import Dict

from ..domain_errors import CollateralInsufficiencyError


class InventoryPool:
    def __init__(self, *, path: str | None = None):
        self.path = str(path or "")
        self._assets: Dict[str, float] = {}
        if self.path:
            self._load()

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            data = json.load(open(self.path, "r", encoding="utf-8")) or {}
            if isinstance(data, dict):
                self._assets = {str(k): float(v) for k, v in data.items()}
        except (OSError, ValueError, TypeError):
            self._assets = {}

    def _save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._assets, f, indent=2, sort_keys=True)

    def seed(self, asset: str, amount: float) -> None:
        self._assets[str(asset)] = float(amount)
        self._save()

    def snapshot(self) -> Dict[str, float]:
        return {k: round(v, 8) for k, v in self._assets.items()}

    def reserve(self, asset: str, amount: float, *, strict: bool = False) -> bool:
        have = float(self._assets.get(str(asset), 0.0))
        if have < float(amount):
            if strict:
                raise CollateralInsufficiencyError(
                    "insufficient inventory", reason_code="inventory_insufficient"
                )
            return False
        self._assets[str(asset)] = have - float(amount)
        self._save()
        return True

    def release(self, asset: str, amount: float) -> None:
        self._assets[str(asset)] = float(self._assets.get(str(asset), 0.0)) + float(amount)
        self._save()
