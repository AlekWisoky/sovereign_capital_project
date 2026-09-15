from __future__ import annotations

from typing import Iterable


# These are the only providers with a canonical executor/calldata path on main.
EXECUTABLE_FLASHLOAN_PROVIDERS: tuple[str, ...] = ("aave", "balancer")
_EXECUTABLE = frozenset(EXECUTABLE_FLASHLOAN_PROVIDERS)


def normalize_flashloan_provider(provider: object) -> str:
    return str(provider or "").strip().lower()


def is_executable_flashloan_provider(provider: object) -> bool:
    return normalize_flashloan_provider(provider) in _EXECUTABLE


def filter_executable_flashloan_providers(providers: Iterable[object]) -> list[str]:
    result: list[str] = []
    for provider in providers:
        normalized = normalize_flashloan_provider(provider)
        if normalized in _EXECUTABLE and normalized not in result:
            result.append(normalized)
    return result
