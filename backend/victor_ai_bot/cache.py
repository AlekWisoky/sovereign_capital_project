from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass
class PerBlockCache:
    _key: Tuple[int, int] | None = None  # (chain_id, block_number)
    _data: Dict[str, Any] = field(default_factory=dict)

    def reset_if_new_block(self, chain_id: int, block_number: int) -> None:
        k = (chain_id, block_number)
        if self._key != k:
            self._key = k
            self._data.clear()

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def stats(self) -> dict:
        return {"entries": len(self._data), "key": self._key}
